package cjmcp

import stdx.log.LogLevel
import stdx.logger.SimpleLogger
import std.env.getStdErr
import server.*

main(args: Array<String>): Int64 {
    let logger = SimpleLogger(getStdErr())
    logger.level = LogLevel.INFO

    CjMcpServer(StdioJsonRpcTransport(logger), logger).serve().code()
}
