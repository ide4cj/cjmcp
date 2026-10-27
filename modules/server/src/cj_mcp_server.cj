package server

import stdx.log.Logger
import jsonrpc.*
import fjson.*

public class CjMcpServer <: McpServer {
    public CjMcpServer(
        private let jrpc: JsonRpcTransport,
        private let logger: Logger
    ) {
    
    }

    public func serve(): ExitCode {
        let connection = Connection(jrpc, this, logger)
        connection.serve()

        ExitCode.SUCCESS
    }

    public func onRequest(request: InboundRequest): Unit {
        logger.info("on request")
    }

    public func onNotification(method: String, params: ?RawJson): Unit {
        logger.info("on notification")
    }
}
