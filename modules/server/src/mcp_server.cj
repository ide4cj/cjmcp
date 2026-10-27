package server

import jsonrpc.*
import stdx.log.Logger

public interface McpServer <: Handler {
    public func serve(): ExitCode
}
