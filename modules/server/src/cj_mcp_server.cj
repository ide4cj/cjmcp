package server

import jsonrpc.*
import stdx.log.Logger

public class CjMcpServer <: McpServer {
    public CjMcpServer(
        private let jrpc: JsonRpcTransport,
        private let logger: Logger
    ) {
    
    }

    public func serve(): ExitCode {
        let connection = Connection(jrpc, this, logger)
        connection.serve()
    }

    public func onRequest(request: InboundRequest): Unit {
        
    }

    public func onNotification(method: String, params: ?RawJson): Unit {
        
    }

    
}
