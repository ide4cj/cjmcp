package server

import std.io.*
import std.sync.{AtomicBool, Mutex}
import jsonrpc.*
import fjson.*

public class StdioJsonRpcTransport <: JsonRpcTransport {

    public static const BODY_BYTES_MAX: Int64 = 32 * 1024 * 1024
    private static const WRITER_KEPT_MAX: Int64 = 1024 * 1024

    private let input: BufferedInputStream<InputStream>
    private let output: BufferedOutputStream<OutputStream>
    private let closed = AtomicBool(false)
    // one each, kept from message to message: only the read loop reads, and writes take `writing`
    private let reader = FjReader(Array<Byte>())
    private var writer = FjWriter()
    private let writing = Mutex()

    /**
     * @param bodyBytesMax - the largest content read; one over it is skipped and refused
     */
    public StdioJsonRpcTransport(
        private let source: InputStream,
        private let sink: OutputStream,
        private let logger: Logger,
        private let bodyBytesMax!: Int64 = BODY_BYTES_MAX
    ) {
        this.input = BufferedInputStream(source, bodyBytesMax)
        this.output = BufferedOutputStream(sink)
    }

    public func isClosed(): Bool {
        closed.load()
    }

    public func close(): Unit {
        if (closed.swap(true)) {
            return
        }

        try {
            output.flush()
        } catch (e: Exception) {
            // a close that throws would mask whatever is being torn down alongside it
            logger.warn("flushing the JSON-RPC transport on close failed", [("cause", e)])
        }

        if (let closeableSink: Resource <- sink) {
            closeableSink.close()
        }
        if (let closeableSource: Resource <- source) {
            closeableSource.close()
        }
    }

    /**
     * A closed transport reads as EOF: shutting down is not a framing fault, and a read loop
     * that already ends on `None` needs no second exit. A header cut off by the stream's end
     * is EOF too, as nothing can tell it from one.
     *
     * @throws RpcException - if the frame carries no decodable message, or is over the limit
     * @throws TransportException - if the framing is malformed or truncated
     */
    public func read(): ?Body {
        match (read(NO_PARAMS_READER)) {
            case Some((body, _)) => body
            case None => None
        }
    }

    public func read(paramsReader: (String) -> Option<(FjReader) -> Any>): ?(Body, ?Any) {
        if (isClosed()) {
            return None
        }
        let payload = match (readLine()) {
            case Some(data) => data
            case None => throw RpcException(ErrorCode.PARSE_ERROR, "JSON-RPC frame declares an empty content")
        }
        reader.reset(payload)
        try {
            let message = Body.read(reader, paramsReader)
            reader.end()
            message
        } catch (e: FjException) {
            // read in one pass, a message does not say which it failed at: the JSON or the message
            if (!isJson(payload)) {
                throw RpcException(ErrorCode.PARSE_ERROR, "JSON-RPC content is not valid JSON\nCause: ${e.message}")
            }
            throw RpcException(ErrorCode.INVALID_REQUEST, "JSON-RPC content is not a valid message\nCause: ${e.message}")
        }
    }

    /**
     * @throws TransportException - if the transport is closed
     */
    public func write(msg: Body): Unit {
        if (isClosed()) {
            throw TransportException("JSON-RPC transport is closed")
        }
        synchronized(writing) {
            writer.clear()
            msg.toJson(writer)
            let payload = writer.bytes()
            output.write(payload)
            output.flush()
            // one outsized answer must not keep its buffer for the lifetime of the connection
            if (payload.size > WRITER_KEPT_MAX) {
                writer = FjWriter()
            }
        }
    }

    private static func isJson(payload: Array<Byte>): Bool {
        try {
            let r = FjReader(payload)
            r.skipValue()
            r.end()
            true
        } catch (m: FjException) {
            false
        }
    }

    /**
     * @throws TransportException - if the stream ends first
     */
    private func readLine(): ?Array<Byte> {
        let bytes = ArrayList<Byte>()
        while (let Some(byte) <- input.readByte()) {
            if (byte == b'\n') {
                break
            }
            bytes.add(byte)
        }
        if (bytes.isEmpty()) {
            return None
        }
        if (bytes.last == b'\r') {
            return unsafe { bytes.slice(0..bytes.size - 1).getRawArray() }
        }
        return unsafe { bytes.slice(0..bytes.size).getRawArray() }
    }
}
