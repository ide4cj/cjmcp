package server

import jsonrpc.*

extend ErrorCode {
    static prop HEADER_MISMATCH: ErrorCode {
        get() {
            ErrorCode(-32020)
        }
    }
    
    static prop MISSED_REQUIRED_CLIENT_CAPABILITY: ErrorCode {
        get() {
            ErrorCode(-32021)
        }
    }
    
    static prop UNSUPPORTED_PROTOCOL_VERSION: ErrorCode {
        get() {
            ErrorCode(-32022)
        }
    }
    
    static prop SERVER_NOT_INITIALIZED: ErrorCode {
        get() {
            ErrorCode(-31000)
        }
    }

}
