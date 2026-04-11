import app from '../hono/hono';
import result from '../model/result';
import { email as receiveEmail } from '../email/email';

function stringToReadableStream(value) {
	return new ReadableStream({
		start(controller) {
			controller.enqueue(new TextEncoder().encode(value));
			controller.close();
		}
	});
}

app.post('/internal/smtp/receive', async (c) => {
	const token = c.req.header('x-smtp-gateway-token');
	if (token !== c.env.smtp_gateway_token) {
		return c.json(result.fail('invalid smtp gateway token', 403));
	}

	const payload = await c.req.json();
	const recipients = Array.isArray(payload.to) ? payload.to : [];
	if (recipients.length === 0) {
		return c.json(result.fail('no recipients', 400));
	}

	for (const recipient of recipients) {
		const message = {
			to: recipient,
			raw: stringToReadableStream(payload.raw || ''),
			setReject(reason) {
				throw new Error(reason);
			},
			async forward() {
				return;
			}
		};
		await receiveEmail(message, c.env, c.executionCtx);
	}

	return c.json(result.ok());
});
