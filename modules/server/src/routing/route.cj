package server.routing

import fjson.RawJson

public interface Route {
    public static prop method: String

    public static func from(body: RawJson): Route
}

public interface Request <: Route {
    
}

public interface Notification <: Route {
    
}


public class InitializeRequest <: Request {
    public static prop method: String {
        get() { "initialize" }
    }
    
    public static func from(body: RawJson): InitializeRequest {
        return InitializeRequest()
    }

}
