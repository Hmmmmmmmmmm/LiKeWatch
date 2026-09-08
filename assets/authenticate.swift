import Foundation
import LocalAuthentication
let context = LAContext()
var error: NSError?
guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else { exit(2) }
context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: "View or copy the LiKeWatch Telegram bot token") { success, _ in
    exit(success ? 0 : 1)
}
RunLoop.main.run()
