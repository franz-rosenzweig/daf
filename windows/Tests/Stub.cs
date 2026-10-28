using System.Net;
using System.Net.Sockets;
using System.Text;

/// <summary>A Daf that answers what the tests tell it to, on 127.0.0.1, and remembers what it was asked.</summary>
sealed class Stub : IDisposable
{
    public sealed record Request(string Method, string Path, Dictionary<string, string> Headers, byte[] Body);
    public sealed record Response(int Status, byte[] Body, string Type = "application/json", Dictionary<string, string>? Headers = null);

    readonly TcpListener listener = new(IPAddress.Loopback, 0);
    readonly Func<Request, Response> answer;
    public readonly List<Request> Asked = [];
    public Uri Base { get; }

    public Stub(Func<Request, Response> answer)
    {
        this.answer = answer;
        listener.Start();
        Base = new Uri($"http://127.0.0.1:{((IPEndPoint)listener.LocalEndpoint).Port}");
        _ = Task.Run(Serve);
    }

    public static Response Json(string json, int status = 200) => new(status, Encoding.UTF8.GetBytes(json));
    public static Response Bytes(byte[] data, string type) => new(200, data, type);

    async Task Serve()
    {
        while (true)
        {
            TcpClient client;
            try { client = await listener.AcceptTcpClientAsync(); }
            catch (Exception) { return; }
            _ = Task.Run(() => One(client));
        }
    }

    async Task One(TcpClient client)
    {
        using (client)
        {
            var stream = client.GetStream();
            var head = new List<byte>();
            var one = new byte[1];
            while (!(head.Count >= 4 && head[^4] == '\r' && head[^3] == '\n' && head[^2] == '\r' && head[^1] == '\n'))
            {
                if (await stream.ReadAsync(one) == 0) return;
                head.Add(one[0]);
            }
            var lines = Encoding.UTF8.GetString(head.ToArray()).Split("\r\n", StringSplitOptions.RemoveEmptyEntries);
            var first = lines[0].Split(' ');
            var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var line in lines.Skip(1))
            {
                var i = line.IndexOf(':');
                if (i > 0) headers[line[..i].Trim()] = line[(i + 1)..].Trim();
            }
            var body = new byte[headers.TryGetValue("Content-Length", out var n) ? int.Parse(n) : 0];
            var got = 0;
            while (got < body.Length)
            {
                var r = await stream.ReadAsync(body.AsMemory(got));
                if (r == 0) break;
                got += r;
            }
            var request = new Request(first[0], first[1], headers, body);
            lock (Asked) Asked.Add(request);
            Response response;
            try { response = answer(request); }
            catch (Exception e) { response = new Response(500, Encoding.UTF8.GetBytes(e.Message), "text/plain"); }
            var sb = new StringBuilder();
            sb.Append($"HTTP/1.1 {response.Status} {(response.Status == 200 ? "OK" : "Not OK")}\r\n");
            sb.Append($"Content-Type: {response.Type}\r\nContent-Length: {response.Body.Length}\r\nConnection: close\r\n");
            foreach (var (k, v) in response.Headers ?? new Dictionary<string, string>()) sb.Append($"{k}: {v}\r\n");
            sb.Append("\r\n");
            await stream.WriteAsync(Encoding.UTF8.GetBytes(sb.ToString()));
            await stream.WriteAsync(response.Body);
        }
    }

    public int Count(string pathStart)
    {
        lock (Asked) return Asked.Count(a => a.Path.StartsWith(pathStart, StringComparison.Ordinal));
    }

    public void Dispose() => listener.Stop();
}
