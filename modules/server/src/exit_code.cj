package server

public enum ExitCode {
    | SUCCESS
    | FAILURE;

    public func code(): Int64 {
        match (this) {
            case SUCCESS => 0
            case FAILURE => 1
        }
    }
}
