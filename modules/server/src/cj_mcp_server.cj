package server

import stdx.log.Logger
import jsonrpc.*
import fjson.*
import server.routing.*

enum ServerState {
    | UNINITIALIZED
    | INITIALIZED
    | EXITING
    | EXITED
}

public class CjMcpServer <: McpServer {
    private var state = ServerState.UNINITIALIZED
    
    public CjMcpServer(
        private let jrpc: JsonRpcTransport,
        private let router: Router,
        private let logger: Logger
    ) {
    
    }

    public func serve(): ExitCode {
        let connection = Connection(jrpc, this, logger)
        logger.info("starting server")
        connection.serve()

        ExitCode.SUCCESS
    }

    public func onRequest(request: InboundRequest): Unit {
        let logger = logger.withAttrs([("method", request.method), ("id", request.id.toString())])
        if (let Some(refusal) <- refusalOf(request.method)) {
            logger.debug("refused", [("reason", refusal.message)])
            request.respond(ResultOrError.Error(refusal))
            return
        }
        logger.info("on request: id=${request.id}, method: ${request.method}")

        request.respond(ResultOrError.Error(ResponseError(ErrorCode.METHOD_NOT_FOUND, "not supported")))
    }

    public func onNotification(method: String, params: ?RawJson): Unit {
        logger.info("on notification")
    }
    
    private func refusalOf(method: String): ?ResponseError {
        match (state) {
            case UNINITIALIZED where method != InitializeRequest.method =>
                ResponseError(ErrorCode.SERVER_NOT_INITIALIZED, "the server is not initialized yet")
            case Initialized where method == InitializeRequest.method =>
                ResponseError(ErrorCode.INVALID_REQUEST, "the server is already initialized")
            case EXITING | EXITED =>
                ResponseError(ErrorCode.INVALID_REQUEST, "the server is shutting down")
            case _ => None
        }
    }
}
