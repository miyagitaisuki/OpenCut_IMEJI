//! Client for the lesson job server (`python scripts/lesson_jobs.py serve`): a small HTTP/1.1 client over
//! std::net, for 127.0.0.1 only. The MCP tools use it to submit lessons and read their status; there is
//! deliberately no tool here that uploads to YouTube.

use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

use serde_json::Value;

/// Where the job server listens: LESSON_JOBS_URL, else http://127.0.0.1:8790.
pub fn base_url() -> String {
    std::env::var("LESSON_JOBS_URL").unwrap_or_else(|_| "http://127.0.0.1:8790".into())
}

/// One request; returns the JSON body on 2xx, or the server's error text.
pub fn request(method: &str, path: &str, body: Option<&Value>) -> Result<Value, String> {
    let url = base_url();
    let host = url
        .strip_prefix("http://")
        .ok_or_else(|| format!("LESSON_JOBS_URL must start with http:// (got {url})"))?
        .trim_end_matches('/')
        .to_string();
    let payload = body.map(|b| b.to_string()).unwrap_or_default();
    let head = format!(
        "{method} {path} HTTP/1.1\r\nHost: {host}\r\nContent-Type: application/json\r\n\
         Content-Length: {}\r\nConnection: close\r\n\r\n",
        payload.len()
    );
    let mut stream = TcpStream::connect(&host)
        .map_err(|error| format!("cannot reach the lesson job server at {host}: {error}"))?;
    stream.set_read_timeout(Some(Duration::from_secs(30))).ok();
    stream
        .write_all(head.as_bytes())
        .and_then(|_| stream.write_all(payload.as_bytes()))
        .map_err(|error| format!("write to the job server failed: {error}"))?;
    let mut raw = String::new();
    stream
        .read_to_string(&mut raw)
        .map_err(|error| format!("read from the job server failed: {error}"))?;
    let (head, body) = raw.split_once("\r\n\r\n").ok_or("the job server sent no HTTP body")?;
    let status: u16 = head
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse().ok())
        .ok_or("the job server sent a bad status line")?;
    let value: Value = serde_json::from_str(body).unwrap_or(Value::String(body.to_string()));
    if (200..300).contains(&status) {
        Ok(value)
    } else {
        Err(format!("job server answered {status}: {}", value))
    }
}

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::net::TcpListener;

    /// Answers one request with `reply` and returns the request text it received.
    fn serve_once(reply: &'static str) -> (String, std::thread::JoinHandle<String>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let handle = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            // Read the whole request (headers and the Content-Length body) before answering.
            let mut raw = Vec::new();
            let mut buf = [0u8; 1024];
            loop {
                let n = stream.read(&mut buf).unwrap();
                raw.extend_from_slice(&buf[..n]);
                let text = String::from_utf8_lossy(&raw).into_owned();
                if let Some((head, body)) = text.split_once("\r\n\r\n") {
                    let length: usize = head
                        .lines()
                        .find_map(|l| l.strip_prefix("Content-Length: "))
                        .and_then(|v| v.trim().parse().ok())
                        .unwrap_or(0);
                    if body.len() >= length || n == 0 {
                        break;
                    }
                }
                if n == 0 {
                    break;
                }
            }
            stream.write_all(reply.as_bytes()).unwrap();
            // Send the FIN, then wait for the client to close: dropping the socket first can reset the reply.
            stream.shutdown(std::net::Shutdown::Write).unwrap();
            let mut rest = Vec::new();
            let _ = stream.read_to_end(&mut rest);
            String::from_utf8_lossy(&raw).into_owned()
        });
        (url, handle)
    }

    #[test]
    fn posts_json_and_reads_the_reply() {
        let (url, server) = serve_once(
            "HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: 15\r\n\r\n{\"status\":\"q\"}\n\n",
        );
        unsafe { std::env::set_var("LESSON_JOBS_URL", &url) };
        let body = serde_json::json!({"questions": [7323]});
        let value = super::request("POST", "/jobs", Some(&body)).unwrap();
        assert_eq!(value["status"], "q");
        let received = server.join().unwrap();
        assert!(received.starts_with("POST /jobs HTTP/1.1"));
        assert!(received.contains("{\"questions\":[7323]}"));
        server_errors_are_returned_as_text();
    }

    fn server_errors_are_returned_as_text() {
        let (url, server) = serve_once(
            "HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\nContent-Length: 22\r\n\r\n{\"error\":\"no such job\"}",
        );
        unsafe { std::env::set_var("LESSON_JOBS_URL", &url) };
        let error = super::request("GET", "/jobs/x", None).unwrap_err();
        assert!(error.contains("404") && error.contains("no such job"));
        server.join().unwrap();
    }
}
