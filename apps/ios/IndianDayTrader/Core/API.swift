import Foundation
import Security

struct Connection: Equatable {
    var url: String
    var token: String

    var isConfigured: Bool { !url.isEmpty && !token.isEmpty }

    /// Parses `idt://pair?u=<url>&t=<token>` printed as a QR code by `idt serve`.
    static func fromPairing(_ uri: URL) -> Connection? {
        guard uri.scheme == "idt", uri.host == "pair",
              let items = URLComponents(url: uri, resolvingAgainstBaseURL: false)?.queryItems,
              let u = items.first(where: { $0.name == "u" })?.value, !u.isEmpty,
              let t = items.first(where: { $0.name == "t" })?.value, !t.isEmpty else { return nil }
        return Connection(url: u, token: t)
    }
}

/// Server URL in UserDefaults, token in the Keychain. Launch arguments
/// `-idtURL` / `-idtToken` (UserDefaults argument domain) seed a demo connection.
enum ConnectionStore {
    private static let urlKey = "idt.url"
    private static let service = "com.iamsanaur.indiandaytrader"

    static func load() -> Connection {
        let d = UserDefaults.standard
        let url = d.string(forKey: urlKey) ?? d.string(forKey: "idtURL") ?? ""
        let token = keychainRead() ?? d.string(forKey: "idtToken") ?? ""
        return Connection(url: url, token: token)
    }

    static func save(_ c: Connection) {
        UserDefaults.standard.set(c.url, forKey: urlKey)
        keychainWrite(c.token)
    }

    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "token"]
    }

    private static func keychainRead() -> String? {
        var q = query
        q[kSecReturnData as String] = true
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func keychainWrite(_ token: String) {
        SecItemDelete(query as CFDictionary)
        var q = query
        q[kSecValueData as String] = Data(token.utf8)
        q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(q as CFDictionary, nil)
    }
}

struct APIError: LocalizedError {
    var message: String
    var status: Int
    var errorDescription: String? { message }
}

struct APIClient {
    var connection: Connection

    static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    private func request(_ path: String, method: String, body: [String: Any]?) throws -> URLRequest {
        let base = connection.url.trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
        guard let url = URL(string: "\(base)/api\(path)") else { throw APIError(message: "Invalid server URL", status: 0) }
        var r = URLRequest(url: url, timeoutInterval: 30)
        r.httpMethod = method
        r.setValue("Bearer \(connection.token)", forHTTPHeaderField: "Authorization")
        if let body {
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        return r
    }

    func call<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil) async throws -> T {
        guard connection.isConfigured else { throw APIError(message: "Not paired. Open More › Settings and scan the QR from idt serve.", status: 0) }
        let (data, resp) = try await URLSession.shared.data(for: request(path, method: method, body: body))
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            let msg = status == 401 ? "Token rejected. Re-pair in Settings." : (obj?["error"] as? String ?? obj?["detail"] as? String ?? "HTTP \(status)")
            throw APIError(message: msg, status: status)
        }
        return try Self.decoder.decode(T.self, from: data)
    }

    func post<T: Decodable>(_ path: String, _ body: [String: Any] = [:]) async throws -> T {
        try await call(path, method: "POST", body: body)
    }

    /// Server-sent events: yields (event, data) pairs until cancelled.
    func events(interval: Int = 15) -> AsyncThrowingStream<(String, Data), Error> {
        AsyncThrowingStream { cont in
            let task = Task {
                do {
                    var r = try request("/events?interval=\(interval)", method: "GET", body: nil)
                    r.timeoutInterval = 3600
                    let (bytes, _) = try await URLSession.shared.bytes(for: r)
                    var event = "message"
                    for try await line in bytes.lines {
                        if line.hasPrefix("event:") { event = line.dropFirst(6).trimmingCharacters(in: .whitespaces) }
                        else if line.hasPrefix("data:") {
                            cont.yield((event, Data(line.dropFirst(5).trimmingCharacters(in: .whitespaces).utf8)))
                            event = "message"
                        }
                    }
                    cont.finish()
                } catch { cont.finish(throwing: error) }
            }
            cont.onTermination = { _ in task.cancel() }
        }
    }
}

@MainActor
final class AppModel: ObservableObject {
    @Published var connection: Connection = ConnectionStore.load()
    @Published var status: Status?
    @Published var lastAlert: AlertItem?

    var api: APIClient { APIClient(connection: connection) }

    func pair(_ c: Connection) {
        connection = c
        ConnectionStore.save(c)
        Task { await refreshStatus() }
    }

    func refreshStatus() async {
        status = try? await api.call("/status")
    }
}
