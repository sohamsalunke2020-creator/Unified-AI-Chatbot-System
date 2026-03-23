# 🚀 Quick Start Guide

Get the Unified Chatbot running in 5 minutes!

## Prerequisites

- Python 3.8+
- Windows/Mac/Linux
- ~3GB disk space
- Internet connection

## Installation

### 1️⃣ Setup Python Environment (1 min)

```bash
# Navigate to project directory
cd d:\ChatBot

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
```

### 2️⃣ Install Dependencies (2 mins)

```bash
# Install all required packages
pip install -r requirements.txt

# Download NLP models
python -m spacy download en_core_web_sm
```

### 3️⃣ Configure API Keys (1 min)

```bash
# Copy example config
cp .env.example .env

# Edit .env and add your keys:
# - Get GOOGLE_GEMINI_API_KEY from https://ai.google.dev/
# - GOOGLE_VISION_API_KEY is not required for the current Task 2 implementation
```

### 4️⃣ Run Setup (1 min)

```bash
python setup.py
```

## ✅ Launch

### Option A: Web Interface (Recommended)
```powershell
./start_streamlit.bat
```

Or:
```powershell
& .\.venv-5\Scripts\python.exe -m streamlit run ui\streamlit_app.py
```
Opens at `http://localhost:8502`

Note: don’t paste commands that contain `http://_vscodecontentref_/...` — that’s a VS Code internal link, not a file path.

### Option B: Command Line
```bash
python chatbot_main.py
```

## 🎯 First Steps

### Try Medical Q&A
```
You: I have a headache and fever, what should I do?
Chatbot: Based on medical knowledge... [provides medical context with disclaimer]
```

### Try Academic Queries
```
You: Tell me about machine learning applications
Chatbot: Based on recent research... [fetches and summarizes papers]
```

### Try Multi-Language
```
You: ¿Qué es la inteligencia artificial?
Chatbot: [Auto-detects Spanish, responds in Spanish]
```

### Try Image Analysis
```
You: [Upload an image] What do you see?
Chatbot: [Analyzes and describes the image]
```

### Try Image Generation
```
You: Generate an image of a robot reading a book.
Chatbot: [Returns generated image + text summary]
```

Note: Task 2 uses Gemini as the implemented Google multimodal model. PaLM is deprecated and not required.

## 🎛️ Configuration

### For Medical Q&A:
1. Download MedQuAD dataset from https://github.com/abachaa/MedQuAD
2. Extract to `data/medquad/`

### For Academic Papers:
- Automatically fetches from arXiv
- No configuration needed

### Multiple Languages:
- Currently supports: English, Spanish, French, Chinese, Arabic
- Add more in `.env` under `SUPPORTED_LANGUAGES`

## 📊 Streamlit Features

- 💬 Chat interface
- 🌐 Language selector
- 📊 Analytics dashboard
- 💾 Save conversations
- 📈 System metrics
- ℹ️ System information

## 🐛 Common Issues

**"Module not found"**
```bash
# Make sure virtual environment is activated
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
```

**"API key error"**
```
1. Get keys from Google AI Studio
2. Add to .env file
3. Restart the app
```

**"Spacy model not found"**
```bash
python -m spacy download en_core_web_sm
```

## 📖 Full Documentation

See `README.md` for:
- Architecture overview
- Detailed task documentation
- API reference
- Advanced configuration
- Performance tuning

## 🎓 Learning Path

1. **Day 1**: Run the chatbot, explore web interface
2. **Day 2**: Test each of the 6 tasks individually
3. **Day 3**: Configure API keys and custom data
4. **Day 4**: Analyze logs, understand performance
5. **Day 5**: Customize and extend features

## 📚 Example Queries to Try

### Medical Queries:
- "What are symptoms of diabetes?"
- "I have a cough and sore throat"
- "What's the treatment for hypertension?"

### Academic Queries:
- "What's new in deep learning?"
- "Explain neural networks"
- "Recent papers on computer vision"

### Multi-Language Queries:
- "Bonjour, parlez-moi de l'IA"
- "¿Cuál es el futuro de la tecnología?"
- "苏州的天气如何？"

### Sentiment-Based:
- "I'm so excited about AI!" (positive)
- "I'm frustrated with this error" (negative)
- "Just asking a simple question" (neutral)

## 🔍 Monitoring

Check logs for performance:
```bash
# View recent logs
tail -f logs/chatbot.log

# On Windows:
Get-Content logs/chatbot.log -Tail 20 -Wait
```

## 🚀 Next Steps

1. Customize response tone
2. Add custom knowledge base
3. Integrate with additional APIs
4. Deploy to cloud (Azure, AWS, GCP)
5. Create mobile app integration

## 💡 Tips

- Use `status` command in CLI to check system health
- View analytics dashboard for conversation patterns
- Save conversations for future reference
- Monitor resource usage in system info panel

## 🆘 Support

- Check `README.md` troubleshooting section
- Review logs in `logs/chatbot.log`
- Test individual modules with Python API
- Verify API keys are correctly configured

## 📊 Performance Expectations

- Response time: 1-3 seconds
- Medical Q&A: 2 seconds
- Academic papers: 2-3 seconds (first fetch)
- Language detection: < 20ms
- Image analysis: 1-2 seconds

---

**Ready to go?** Run your first command:
```bash
start_streamlit.bat
# Or (manual):
python -m streamlit run ui/streamlit_app.py
```

Happy chatting! 🤖💬
