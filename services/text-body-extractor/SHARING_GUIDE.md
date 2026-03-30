# Sharing Your FastAPI Application Remotely

This guide shows you how to share your Text Body Relationship Extractor with others on different networks.

## Quick Start (Recommended)

1. **Start your FastAPI server**:
   ```bash
   python run_fastapi.py
   ```

2. **Share your application** (choose one):
   - **ngrok:** `python share_app.py`
   - **localtunnel:** `./share_localtunnel.sh` or `npx localtunnel --port 5000`

3. **Share the generated URL** with others

## Manual Method

### Option 1: Using ngrok (Easiest)

1. **Install ngrok** (if not already installed):
   ```bash
   brew install ngrok/ngrok/ngrok
   ```

2. **Start your FastAPI server**:
   ```bash
   python run_fastapi.py
   ```

3. **Create a tunnel**:
   ```bash
   ngrok http 5000
   ```

4. **Share the public URL** that ngrok provides

### Option 2: Using Cloudflare Tunnel

1. **Install cloudflared**:
   ```bash
   brew install cloudflared
   ```

2. **Start your FastAPI server**:
   ```bash
   python run_fastapi.py
   ```

3. **Create a tunnel**:
   ```bash
   cloudflared tunnel --url http://localhost:5000
   ```

### Option 3: Using localtunnel

1. **Install localtunnel**:
   ```bash
   npm install -g localtunnel
   ```

2. **Start your FastAPI server**:
   ```bash
   python run_fastapi.py
   ```

3. **Create a tunnel**:
   ```bash
   lt --port 5000
   ```

## Security Considerations

### ⚠️ Important Security Notes

1. **Public Access**: Anyone with the URL can access your application
2. **API Keys**: Keep your API keys secure and don't share them
3. **Temporary URLs**: These URLs change each time you restart the tunnel
4. **Rate Limiting**: Consider adding rate limiting for public access
5. **Authentication**: For production use, consider adding authentication

### 🔒 Making it More Secure

1. **Add Basic Authentication**:
   ```python
   # In app_fastapi.py, add authentication middleware
   from fastapi import HTTPException, Depends
   from fastapi.security import HTTPBasic, HTTPBasicCredentials
   
   security = HTTPBasic()
   
   def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
       if credentials.username != "user" or credentials.password != "password":
           raise HTTPException(status_code=401, detail="Invalid credentials")
       return credentials
   ```

2. **Use Environment Variables**:
   ```bash
   export API_USERNAME=your_username
   export API_PASSWORD=your_secure_password
   ```

3. **Add Rate Limiting**:
   ```bash
   pip install slowapi
   ```

## What to Share with Others

### Essential Information

1. **Application URL**: The public URL provided by your tunnel
2. **API Documentation**: URL + `/docs` for interactive documentation
3. **Usage Instructions**: Basic how-to guide

### Example Share Message

```
Hi! I've set up a Text Body Relationship Extractor for you to use:

🌐 Application: https://abc123.ngrok.io
📚 API Docs: https://abc123.ngrok.io/docs
📖 ReDoc: https://abc123.ngrok.io/redoc

Features:
- Extract entities and relationships from text
- Analyze content from URLs
- Download results as CSV files
- Works with Ollama (local), Gemini, and OpenAI

To use:
1. Open the application URL in your browser
2. Choose your model (Ollama recommended for no API key)
3. Enter text or a URL to analyze
4. View and download results

The URL will change if I restart the server, so let me know if it stops working!
```

## Troubleshooting

### Common Issues

1. **"Connection refused"**:
   - Make sure your FastAPI server is running
   - Check if the port is correct (default: 5000)

2. **"ngrok not found"**:
   - Install ngrok: `brew install ngrok/ngrok/ngrok`

3. **"Tunnel not working"**:
   - Check if port 5000 is available
   - Try a different port: `ngrok http 5002`

4. **"URL not accessible"**:
   - Wait a few seconds for ngrok to fully start
   - Check the ngrok dashboard at http://localhost:4040

### Getting Help

- **ngrok Dashboard**: http://localhost:4040 (when ngrok is running)
- **FastAPI Docs**: http://localhost:5000/docs
- **Server Logs**: Check the terminal where you started the server

## Alternative Deployment Options

### For More Permanent Solutions

1. **Heroku**: Deploy to cloud platform
2. **Railway**: Simple cloud deployment
3. **DigitalOcean**: VPS deployment
4. **AWS/GCP/Azure**: Cloud infrastructure

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "run_fastapi.py"]
```

## Monitoring Usage

### Check Who's Using Your App

1. **ngrok Dashboard**: http://localhost:4040
2. **Server Logs**: Watch the terminal output
3. **Add Logging**: Implement request logging in your app

### Example Logging

```python
import logging
from fastapi import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url} from {request.client.host}")
    response = await call_next(request)
    return response
```

## Best Practices

1. **Use HTTPS**: ngrok provides this automatically
2. **Monitor Usage**: Keep an eye on who's accessing your app
3. **Set Time Limits**: Don't leave tunnels open indefinitely
4. **Backup Data**: Save important results locally
5. **Update Regularly**: Keep dependencies updated

## Support

If you need help:
1. Check the troubleshooting section above
2. Look at the FastAPI documentation
3. Check ngrok documentation for tunnel issues
4. Review server logs for error messages 