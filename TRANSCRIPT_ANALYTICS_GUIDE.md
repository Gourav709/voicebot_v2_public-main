# Transcript & Analytics Features

## Overview

The enhanced voicebot now includes two powerful features for tracking and analyzing conversations:

1. **Conversation Transcripts** - Save full conversation history to `.txt` files
2. **Analytics & Reporting** - Track detailed metrics and export to `.xlsx` files

Both features are **fully modular** and controlled via `.env` configuration.

---

## 📝 Conversation Transcripts

### What It Does

Automatically saves every conversation to a human-readable text file with:
- User utterances
- Bot responses
- Timestamps (optional)
- Turn numbers (optional)
- Session metadata

### Configuration

```bash
# Enable/disable transcript logging
ENABLE_TRANSCRIPT=1                  # 1=enabled, 0=disabled

# Output directory
TRANSCRIPT_DIR=./transcripts         # Where to save transcript files

# Formatting options
TRANSCRIPT_TIMESTAMPS=1              # Include timestamps (HH:MM:SS)
TRANSCRIPT_TURN_NUMBERS=1            # Include turn numbers
```

### Example Transcript Output

```
============================================================
CONVERSATION TRANSCRIPT
============================================================
Session ID: 20240209_143052
Started: 2024-02-09 14:30:52
============================================================

--- Turn 1 ---
[14:30:55]
User: When is my SIP due?
Bot: Got it. Your SIP is coming up in a few days. If your e-mandate is set up, please ensure you have enough balance in your bank account before the SIP date. Would you like me to guide you with the steps now?

--- Turn 2 ---
[14:31:15]
User: Yes please
Bot: Sure. First, log into your account...

============================================================
Ended: 2024-02-09 14:35:22
Reason: User stopped session
============================================================
```

### File Naming

Transcripts are automatically named: `conversation_{session_id}.txt`

Example: `conversation_20240209_143052.txt`

### Use Cases

- **Quality Assurance**: Review conversation quality
- **Training**: Train new models or improve scripts
- **Compliance**: Maintain conversation records
- **Debugging**: Understand user interactions
- **Research**: Analyze conversation patterns

---

## 📊 Analytics & Reporting

### What It Does

Tracks comprehensive metrics throughout the conversation and exports to Excel:

**Session Metrics:**
- Duration
- Total turns
- Start/end times

**Audio Metrics:**
- Audio recorded (seconds)
- Barge-ins count
- Denoised utterances

**STT Metrics:**
- Transcriptions count
- Processing time
- Real-time factor
- Errors

**LLM Metrics:**
- API calls
- Tokens used
- Average tokens per turn
- Retries and errors

**TTS Metrics:**
- Syntheses count
- Characters synthesized
- Processing time
- Errors

**Intent Analysis:**
- Intent distribution
- FAQ usage
- Handoff frequency

**Error Tracking:**
- Total errors
- Error types breakdown

### Configuration

```bash
# Enable/disable analytics
ENABLE_ANALYTICS=1                   # 1=enabled, 0=disabled

# Output directory
ANALYTICS_DIR=./analytics            # Where to save analytics files

# Export format
ANALYTICS_FORMAT=xlsx                # Options: xlsx, json, csv
```

### Export Formats

#### 1. Excel (XLSX) - Recommended

**Two sheets:**

**Sheet 1: Session Summary**
- All metrics organized by category
- Easy to read and share
- Professional formatting

**Sheet 2: Turn Details**
- Per-turn breakdown
- Includes user/bot text
- Intent and timing data

**Features:**
- Color-coded headers
- Auto-sized columns
- Formulas for derived metrics

#### 2. JSON

**Structure:**
```json
{
  "metrics": {
    "session_id": "20240209_143052",
    "duration_seconds": 285.4,
    "total_turns": 15,
    "total_tokens_used": 4500,
    ...
  },
  "turn_details": [
    {
      "turn": 1,
      "timestamp": "2024-02-09T14:30:55",
      "user_text": "When is my SIP due?",
      "bot_text": "Got it. Your SIP...",
      "intent": "faq",
      "faq_id": "sip_due_soon",
      "confidence": 0.95,
      "duration_sec": 2.3
    },
    ...
  ]
}
```

**Use for:** Programmatic analysis, data pipelines

#### 3. CSV

**Two files:**
- `analytics_summary_{session_id}.csv` - Metrics summary
- `analytics_turns_{session_id}.csv` - Turn details

**Use for:** Spreadsheet import, data analysis tools

### File Naming

Analytics are automatically named: `analytics_{session_id}.{format}`

Example: `analytics_20240209_143052.xlsx`

### Use Cases

**Performance Monitoring:**
- Track latency trends
- Monitor token usage
- Identify bottlenecks

**Cost Analysis:**
- Calculate API costs (tokens × price)
- Monitor usage patterns
- Budget forecasting

**Quality Metrics:**
- Barge-in frequency (user patience)
- Error rates
- Intent accuracy

**Business Intelligence:**
- Popular FAQs
- Common intents
- User behavior patterns

**Optimization:**
- Identify slow components
- Find high-error areas
- Optimize token usage

---

## 🎯 Usage Examples

### Basic Setup

```bash
# .env configuration
ENABLE_TRANSCRIPT=1
TRANSCRIPT_DIR=./transcripts
TRANSCRIPT_TIMESTAMPS=1

ENABLE_ANALYTICS=1
ANALYTICS_DIR=./analytics
ANALYTICS_FORMAT=xlsx
```

### Production Setup

```bash
# Save everything for analysis
ENABLE_TRANSCRIPT=1
TRANSCRIPT_DIR=./production/transcripts
TRANSCRIPT_TIMESTAMPS=1
TRANSCRIPT_TURN_NUMBERS=1

ENABLE_ANALYTICS=1
ANALYTICS_DIR=./production/analytics
ANALYTICS_FORMAT=xlsx

# Also enable event logging
LOG_EVENTS_TO_FILE=1
EVENTS_FILE=./production/logs/events.jsonl
```

### Development Setup

```bash
# Minimal logging for speed
ENABLE_TRANSCRIPT=0
ENABLE_ANALYTICS=0

# Or keep analytics but skip transcript
ENABLE_TRANSCRIPT=0
ENABLE_ANALYTICS=1
ANALYTICS_FORMAT=json  # Faster than xlsx
```

### Compliance Setup

```bash
# Maximum detail for auditing
ENABLE_TRANSCRIPT=1
TRANSCRIPT_DIR=./compliance/transcripts
TRANSCRIPT_TIMESTAMPS=1
TRANSCRIPT_TURN_NUMBERS=1

ENABLE_ANALYTICS=1
ANALYTICS_DIR=./compliance/analytics
ANALYTICS_FORMAT=xlsx

LOG_EVENTS_TO_FILE=1
LOG_AUDIO_STATS=1
SAVE_AUDIO_FILES=1  # Save actual audio
```

---

## 📈 Analyzing the Data

### Key Metrics to Track

**1. Conversation Duration**
- `duration_seconds` in analytics
- Target: < 300 seconds (5 minutes) for quick queries

**2. Tokens per Turn**
- `avg_tokens_per_turn` in analytics
- Monitor for cost optimization
- Target: < 500 tokens/turn

**3. Real-Time Factor (STT)**
- `stt_real_time_factor` in analytics
- < 1.0 = processing faster than real-time ✓
- > 1.0 = bottleneck ⚠️

**4. Barge-in Rate**
- `total_barge_ins / total_turns`
- High rate → bot responses too slow or too long
- Target: < 20%

**5. Error Rates**
- `stt_errors`, `llm_errors`, `tts_errors`
- Target: < 5% of total turns

**6. Intent Distribution**
- Which FAQs are most common?
- Which intents trigger handoffs?

### Excel Analysis

Open the analytics Excel file and:

1. **Check Summary Tab**
   - Quick overview of session
   - Identify any red flags (high errors, long duration)

2. **Review Turn Details Tab**
   - Filter by intent
   - Sort by duration
   - Find patterns in handoffs

3. **Create Pivot Tables**
   - Intent frequency
   - Error distribution
   - Time series analysis

### Programmatic Analysis (JSON)

```python
import json

# Load analytics
with open('analytics_20240209_143052.json') as f:
    data = json.load(f)

metrics = data['metrics']
turns = data['turn_details']

# Calculate cost (example: $0.50 per 1M tokens)
cost = metrics['total_tokens_used'] / 1_000_000 * 0.50
print(f"Session cost: ${cost:.4f}")

# Find slowest turns
slow_turns = [t for t in turns if t['duration_sec'] > 3.0]
print(f"Slow turns: {len(slow_turns)}")

# Intent breakdown
intents = {}
for turn in turns:
    intent = turn['intent']
    intents[intent] = intents.get(intent, 0) + 1
print("Intent distribution:", intents)
```

---

## 🔄 Workflow Integration

### Daily Reports

**Setup cron job:**
```bash
# Aggregate daily analytics
0 0 * * * python scripts/aggregate_analytics.py
```

**Script example:**
```python
import os
import glob
import pandas as pd

# Find all analytics files from today
files = glob.glob('analytics/*_20240209_*.xlsx')

# Combine into daily report
dfs = [pd.read_excel(f, sheet_name='Session Summary') for f in files]
daily_report = pd.concat(dfs, ignore_index=True)

# Save
daily_report.to_excel('reports/daily_20240209.xlsx', index=False)
```

### Real-Time Monitoring

**Setup dashboard:**
```python
# Monitor key metrics in real-time
from watchdog import observers
from watchdog import events

class AnalyticsMonitor(events.FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith('.json'):
            # New analytics file
            metrics = load_metrics(event.src_path)
            
            # Alert if errors > threshold
            if metrics['total_errors'] > 5:
                send_alert(f"High errors: {metrics['total_errors']}")
            
            # Alert if tokens > threshold
            if metrics['total_tokens_used'] > 10000:
                send_alert(f"High token usage: {metrics['total_tokens_used']}")

observer = observers.Observer()
observer.schedule(AnalyticsMonitor(), path='./analytics', recursive=False)
observer.start()
```

### Cost Tracking

**Calculate costs:**
```python
import glob
import json

# Token costs (example prices)
GROQ_COST_PER_1M = 0.50  # $0.50 per 1M tokens
ELEVENLABS_COST_PER_1K_CHARS = 0.30  # $0.30 per 1K chars

total_cost = 0

for file in glob.glob('analytics/*.json'):
    with open(file) as f:
        data = json.load(f)
    
    # LLM cost
    tokens = data['metrics']['total_tokens_used']
    llm_cost = (tokens / 1_000_000) * GROQ_COST_PER_1M
    
    # TTS cost
    chars = data['metrics']['total_chars_synthesized']
    tts_cost = (chars / 1_000) * ELEVENLABS_COST_PER_1K_CHARS
    
    session_cost = llm_cost + tts_cost
    total_cost += session_cost
    
    print(f"{file}: ${session_cost:.4f}")

print(f"Total cost: ${total_cost:.2f}")
```

---

## 🛠️ Troubleshooting

### Transcript Not Saving

**Check:**
1. `ENABLE_TRANSCRIPT=1` in .env
2. Directory exists and is writable
3. Check console for error messages

**Common issues:**
- Permission denied → Fix directory permissions
- File already exists → Session ID collision (very rare)

### Analytics Export Fails

**Check:**
1. `openpyxl` installed: `pip install openpyxl`
2. Directory is writable
3. Format is valid: `xlsx`, `json`, or `csv`

**Fallback:**
If Excel export fails, it automatically falls back to JSON.

### Large File Sizes

**Transcripts:**
- Typical: 2-5 KB per conversation
- Long sessions: up to 50 KB

**Analytics:**
- XLSX: 10-50 KB per session
- JSON: 5-20 KB per session
- CSV: 3-15 KB per session

**Management:**
```bash
# Archive old files monthly
mkdir -p archives/2024-02
mv transcripts/conversation_202402*.txt archives/2024-02/
mv analytics/analytics_202402*.xlsx archives/2024-02/
```

---

## 🎓 Best Practices

### 1. Enable Both in Production

```bash
ENABLE_TRANSCRIPT=1
ENABLE_ANALYTICS=1
```

Benefits:
- Transcripts for qualitative analysis
- Analytics for quantitative metrics
- Complete conversation records

### 2. Use Excel for Reports

```bash
ANALYTICS_FORMAT=xlsx
```

Benefits:
- Easy to read and share
- Professional formatting
- No additional processing needed

### 3. Regular Backups

```bash
# Daily backup script
rsync -av transcripts/ backups/transcripts/
rsync -av analytics/ backups/analytics/
```

### 4. Monitor Directory Sizes

```bash
# Check sizes weekly
du -sh transcripts/
du -sh analytics/
```

### 5. Analyze Regularly

- Daily: Check for errors and anomalies
- Weekly: Review intent distribution
- Monthly: Cost analysis and optimization

---

## 📊 Sample Analytics Output

### Excel Sheet 1: Session Summary

| Metric | Value |
|--------|-------|
| **Session Information** |
| Session ID | 20240209_143052 |
| Start Time | 2024-02-09 14:30:52 |
| End Time | 2024-02-09 14:35:22 |
| Duration (seconds) | 270 |
| **Conversation Metrics** |
| Total Turns | 12 |
| User Utterances | 12 |
| Bot Responses | 12 |
| Avg Turn Duration (sec) | 22.5 |
| **LLM Metrics** |
| API Calls | 12 |
| Tokens Used | 3,840 |
| Avg Tokens/Turn | 320 |
| **Intent Distribution** |
| faq | 8 |
| handoff | 2 |
| smalltalk | 2 |

### Excel Sheet 2: Turn Details

| Turn | Timestamp | Intent | FAQ ID | Confidence | Duration | User Text | Bot Text |
|------|-----------|--------|--------|------------|----------|-----------|----------|
| 1 | 14:30:55 | faq | sip_due_soon | 0.95 | 2.3 | When is my SIP due? | Got it. Your SIP is... |
| 2 | 14:31:15 | faq | mandate_not_set | 0.88 | 2.1 | How do I set up mandate? | Sure. First, log in... |

---

## 🎯 Summary

**Transcripts:** Human-readable conversation logs
**Analytics:** Detailed metrics and performance data

**Both are:**
- ✅ Fully modular (toggle via .env)
- ✅ Automatic (no code changes needed)
- ✅ Professional output
- ✅ Production-ready

**Perfect for:**
- Quality assurance
- Cost tracking
- Performance monitoring
- Compliance
- Business intelligence

Enable them today with just two lines in your `.env` file!
