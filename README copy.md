# UK Job Search Agent 🤖

Daily automated job search for UK tech roles paying £120k-150k.

## Setup 

1. Get Tavily API key from https://tavily.com
2. Add secrets in GitHub: Settings → Secrets and variables → Actions
   - `TAVILY_API_KEY`  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"
   - `EMAIL_PASSWORD`
   - Aws secret keys 
3. Push to main branch 

## How it works

Runs daily at 9 AM UK time, searches LinkedIn & job boards, emails results.

## License

MIT