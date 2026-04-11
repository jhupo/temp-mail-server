import { SMTPServer } from "smtp-server";
import PostalMime from "postal-mime";

const PORT = Number(process.env.SMTP_GATEWAY_PORT || 25);
const API_BASE = process.env.SMTP_GATEWAY_API_BASE || "http://cloud-mail-app:8000";
const SHARED_TOKEN = process.env.SMTP_GATEWAY_TOKEN || "change_me_gateway_token";

async function parseStream(stream) {
  const chunks = [];
  for await (const chunk of stream) {
    chunks.push(Buffer.from(chunk));
  }
  const raw = Buffer.concat(chunks);
  const parser = new PostalMime();
  const email = await parser.parse(raw);
  return { raw, email };
}

const server = new SMTPServer({
  disabledCommands: ["AUTH"],
  authOptional: true,
  onRcptTo(address, _session, callback) {
    callback(null);
  },
  async onData(stream, session, callback) {
    try {
      const { raw, email } = await parseStream(stream);
      const payload = {
        from: session.envelope.mailFrom?.address || email.from?.address || "",
        to: session.envelope.rcptTo.map((item) => item.address),
        subject: email.subject || "",
        text: email.text || "",
        html: email.html || "",
        raw: raw.toString("utf-8"),
      };

      const response = await fetch(`${API_BASE}/internal/smtp/receive`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-smtp-gateway-token": SHARED_TOKEN,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`receive endpoint failed: ${response.status}`);
      }
      callback(null, "Message accepted");
    } catch (error) {
      callback(error);
    }
  },
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`SMTP gateway listening on ${PORT}`);
});
