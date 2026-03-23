# Advanced Configuration Guide

Complete Configuration Reference for Unified Chatbot System

## Environment Variables (.env file)

### Google AI APIs
```
GOOGLE_PALM_API_KEY=<your_key>
  Purpose: Deprecated legacy key
  Where to get: N/A for current implementation
  Required: NO
  Note: Kept only for backward-compatible documentation. Task 2 uses Gemini as the implemented Google multimodal model.
  
GOOGLE_GEMINI_API_KEY=<your_key>
  Purpose: Gemini text and multimodal assistance for Task 2
  Where to get: https://ai.google.dev/
  Required: Optional for cloud-assisted Task 2 features; local fallbacks work without it
  
GOOGLE_VISION_API_KEY=<your_key>
  Purpose: Reserved optional compatibility setting
  Where to get: Google Cloud Console
  Required: NO for the current Task 2 implementation
```

### Vector Database Configuration
```
VECTOR_DB_TYPE=faiss
  Options: faiss (recommended), chromadb, pinecone
  Default: faiss
  Note: Currently only FAISS is implemented

VECTOR_DB_PATH=./data/vector_db
  Purpose: Where to store vector database files
  Default: ./data/vector_db
  Note: Must have write permissions

EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
  Purpose: Which embedding model to use
  Options:
    - sentence-transformers/all-MiniLM-L6-v2 (fast, 384 dims)
    - sentence-transformers/all-mpnet-base-v2 (better, 768 dims)
    - sentence-transformers/paraphrase-MiniLM-L6-v2
  Default: all-MiniLM-L6-v2
```

### Medical Configuration
```
MEDQUAD_DATA_PATH=./data/medquad
  Purpose: Where MedQuAD dataset is stored
  How to setup:
    1. Download from https://github.com/abachaa/MedQuAD
    2. Extract to data/medquad/
  Note: Optional - basic medical KB included if not provided
```

### ArXiv Configuration
```
ARXIV_DATA_PATH=./data/arxiv
ARXIV_CACHE_PATH=./data/arxiv_cache
  Purpose: Cache for research papers and metadata
```

### Language Settings
```
SUPPORTED_LANGUAGES=en,es,fr,zh,ar
  Current: English, Spanish, French, Chinese, Arabic
  
DEFAULT_LANGUAGE=en
  Purpose: Internal processing language
```

### Model Configuration
```
SENTIMENT_MODEL=distilbert-base-uncased-finetuned-sst-2-english
SENTIMENT_MODEL options:
  - distilbert-base-uncased-finetuned-sst-2-english (default, fast)
  - roberta-base-SST2 (more accurate)
  - bert-base-uncased-finetuned-sst-2-english (slowest, most accurate)

LOCAL_LLM_MODEL=gpt2
  Options: distilgpt2, gpt2, gpt2-medium
```

### Update Configuration
```
UPDATE_INTERVAL_DAYS=7
  Purpose: Days between knowledge base updates
  Range: 1-30 recommended

BATCH_UPDATE_SIZE=100
  Purpose: Documents added per update
  Range: 10-1000
```

### Logging
```
LOG_LEVEL=INFO
  Options: DEBUG, INFO, WARNING, ERROR, CRITICAL

LOG_FILE=./logs/chatbot.log
  Purpose: Log file location
```

## Performance Profiles

### High-Performance (Production)
```ini
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
UPDATE_INTERVAL_DAYS=1
BATCH_UPDATE_SIZE=500
LOG_LEVEL=WARNING
SENTIMENT_MODEL=roberta-base-SST2
```

### Low-Resource
```ini
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
UPDATE_INTERVAL_DAYS=30
BATCH_UPDATE_SIZE=50
LOCAL_LLM_MODEL=distilgpt2
LOG_LEVEL=ERROR
```

### Research/Accuracy
```ini
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
UPDATE_INTERVAL_DAYS=7
BATCH_UPDATE_SIZE=200
LOG_LEVEL=DEBUG
SENTIMENT_MODEL=bert-base-uncased-finetuned-sst-2-english
```

## Model Selection Guide

### Embedding Models
- **all-MiniLM-L6-v2**: 23MB, fastest, good quality (default)
- **all-mpnet-base-v2**: 438MB, slower, best quality
- **paraphrase-MiniLM-L6-v2**: 23MB, fast, good for paraphrases

### Sentiment Models
- **distilbert** (default): Fast, 91-92% accuracy, 268MB
- **roberta-base**: Medium speed, 95%+ accuracy, 498MB
- **bert-base**: Slowest, 96%+ accuracy, 440MB

### LLM Models
- **distilgpt2**: Fastest, basic, 336MB
- **gpt2** (default): Balanced, 548MB
- **gpt2-medium**: Slower, better, 1.5GB

## Performance Tuning

### Reduce Memory Usage
1. Use smaller embedding model
2. Reduce BATCH_UPDATE_SIZE
3. Limit conversation history
4. Use streaming for large responses

### Improve Speed
1. Use all-MiniLM-L6-v2 embedding
2. Use distilbert sentiment model
3. Increase UPDATE_INTERVAL_DAYS
4. Enable caching

### Improve Accuracy
1. Use all-mpnet-base-v2 embedding
2. Use roberta sentiment model
3. Update knowledge base frequently
4. Use larger LLM models

## Security Best Practices

1. **API Keys**: Store in .env, never commit to version control
2. **Input Validation**: All inputs sanitized automatically
3. **Data Privacy**: Medical data handled with care
4. **Production**: Use HTTPS, implement authentication, rate limiting
5. **Key Rotation**: Change API keys regularly

## Monitoring

### Key Metrics
- Response time per query
- API error rates
- Vector DB size growth
- Memory usage
- Cache hit rates
- User satisfaction

### Log Analysis
```bash
# Count errors
grep "ERROR" logs/chatbot.log | wc -l

# Find slow queries
grep "took.*seconds" logs/chatbot.log

# Monitor API usage
grep "API call" logs/chatbot.log
```

## Troubleshooting Configuration

**Out of Memory**: Use smaller models, reduce batch size
**Slow Response**: Use faster models, increase update interval
**Low Accuracy**: Use larger models, update KB frequently
**Storage Issues**: Reduce batch size, archive old logs

---

See README.md for complete documentation
