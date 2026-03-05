# Berengario Quick Start

## Installation (5 minutes)

```bash
# Clone repository
git clone https://github.com/gilestrolab/berengario.git
cd berengario

# Setup Python environment
python -m venv .venv
source .venv/bin/activate

# Install Berengario
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

Add documents to `data/documents/` folder, then:

```bash
berengario --mode process
```

### Query Knowledge Base

```bash
berengario --mode query --query "What are the policies?"
```

### Watch for New Documents

```bash
berengario --mode watch  # Runs continuously
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
berengario --mode query --query "What are the PhD application deadlines?"
```

## Troubleshooting

### Command not found: berengario
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
ls data/documents/
```

## Next Steps

1. **Add your documents** to `data/documents/` folder
2. **Process them**: `berengario --mode process`
3. **Start querying**: `berengario --mode query --query "..."`

See [README.md](README.md) for full documentation.
