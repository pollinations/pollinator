# pollinator
Get tasks from supabase, then run a cog model to finish the task.

# Run locally
Install package:
```sh
# Install dependencies
pip install -e ".[test]"

# Install pre-commit hooks
brew install pre-commit
pre-commit install -t pre-commit
```

Set the supabase API key in your `.env`. Then
```
python pollinator/main.py
```
Or build an run the image:
```
docker build -t pollinator .
docker run --env-file .env pollinator
```

# Tests
1. Build the test model: `cd test-cog-model && cog build -t no-gpu-test-image`
2. Run the tests: `pytest test`
