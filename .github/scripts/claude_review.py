import os
import anthropic
import requests

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

pr_diff = requests.get(
    os.environ['PR_DIFF_URL'],
    headers={'Authorization': f'token {os.environ["GITHUB_TOKEN"]}'},
).text

msg = client.messages.create(
    model='claude-haiku-4-5-20251001',
    max_tokens=1000,
    messages=[{
        'role': 'user',
        'content': (
            f'Review this PR diff for StyleSense:\n{pr_diff[:8000]}\n'
            'Check: missing error handling, hardcoded secrets, missing RLS, India-specific issues.'
        ),
    }],
)

print(msg.content[0].text)
