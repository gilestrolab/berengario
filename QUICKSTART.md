# RAGInbox Quick Start

## Installation (5 minutes)

```bash
# Clone repository
git clone https://github.com/gilestrolab/RAGInbox.git
cd RAGInbox

# Setup Python environment
python -m venv .venv
source .venv/bin/activate

# Install RAGInbox
pip install -e .
```

## Configuration (2 minutes)

Edit `.env` file with your settings:

```bash
# Instance Configuration
INSTANCE_NAME=MyBot
INSTANCE_DESCRIPTION=My helpful assistant
ORGANIZATION=My Company

# API Key (get from https://naga.ac or https://openai.com)
OPENAI_API_KEY=your-key-here
```

## Usage

### Process Documents

Add documents to `Documents/` folder, then:

```bash
raginbox --mode process
```

### Query Knowledge Base

```bash
raginbox --mode query --query "What are the policies?"
```

### Watch for New Documents

```bash
raginbox --mode watch  # Runs continuously
```

## Example: DoLS-GPT Instance

```bash
# .env configuration
INSTANCE_NAME=DoLS-GPT
INSTANCE_DESCRIPTION=AI assistant for Department of Life Sciences
ORGANIZATION=Imperial College London
OPENAI_API_KEY=ng-your-naga-key
```

Query example:
```bash
raginbox --mode query --query "What are the PhD application deadlines?"
```

## Troubleshooting

### Command not found: raginbox
```bash
# Reinstall package
pip install -e .
```

### API errors
```bash
# Check .env file exists and has valid API key
cat .env | grep OPENAI_API_KEY
```

### No documents found
```bash
# Check documents path
ls Documents/
```

## Next Steps

1. **Add your documents** to `Documents/` folder
2. **Process them**: `raginbox --mode process`
3. **Start querying**: `raginbox --mode query --query "..."`

See [README.md](README.md) for full documentation.
