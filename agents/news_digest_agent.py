#!/usr/bin/env python3
"""
Daily News Digest Agent
Collects and summarizes news about topics you care about.
"""

import os
import re
import logging
from datetime import datetime

from agents.base_agent import BaseAgent
from config.settings import Settings

logger = logging.getLogger(__name__)


class NewsDigestAgent(BaseAgent):
    def __init__(self):
        """Initialize the news digest agent."""
        if not Settings.has_search_configured():
            raise ValueError("BRAVE_API_KEY not found in .env")

        super().__init__()

        self.brave_key = Settings.BRAVE_API_KEY
        self.resend_key = Settings.RESEND_API_KEY
        self.email_from = Settings.EMAIL_FROM
        self.email_to = Settings.EMAIL_TO

    def search_news(self, topic, num_results=5):
        """Search for recent news about a topic using Brave Search."""
        logger.info("Searching news about: %s", topic)

        try:
            import requests
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.brave_key
            }
            params = {
                "q": f"{topic} news",
                "count": num_results,
                "freshness": "pd"  # Past day
            }

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            # Extract results
            articles = []
            for item in data.get("web", {}).get("results", [])[:num_results]:
                articles.append({
                    "title": item.get("title"),
                    "snippet": item.get("description"),
                    "url": item.get("url"),
                    "age": item.get("age", "")
                })

            logger.info("Found %d articles for '%s'", len(articles), topic)
            return articles

        except Exception as e:
            logger.error("Error searching for '%s': %s", topic, e)
            return []

    def generate_digest(self, topics_with_articles):
        """Use Claude to generate a news digest from collected articles."""
        logger.info("Generating digest with Claude...")

        # Prepare the content for Claude
        digest_content = "# News Articles Collected\n\n"

        for topic, articles in topics_with_articles.items():
            digest_content += f"\n## Topic: {topic}\n\n"
            if articles:
                for i, article in enumerate(articles, 1):
                    digest_content += f"{i}. **{article['title']}**\n"
                    digest_content += f"   {article['snippet']}\n"
                    digest_content += f"   URL: {article['url']}\n"
                    if article.get('age'):
                        digest_content += f"   Age: {article['age']}\n"
                    digest_content += "\n"
            else:
                digest_content += "No recent articles found.\n\n"

        # Ask Claude to synthesize a digest
        today_date = datetime.now().strftime('%B %d, %Y')
        prompt = f"""You are a news analyst creating a daily digest for {today_date}. Based on the following news articles, create a well-organized, informative summary.

{digest_content}

Please create a daily news digest that:
1. Summarizes the key developments for each topic
2. Highlights the most important or interesting stories
3. Provides context and connections between stories when relevant
4. Uses a professional but engaging tone
5. Includes relevant URLs for readers who want more details
6. DO NOT include a date header or title - just start with the content organized by topic

Format the digest in clean markdown with headers (start with ##), bullet points, and links. Do not include a top-level # header."""

        try:
            response = self.call_claude(messages=prompt)

            digest_text = response.content[0].text
            logger.info("Digest generated successfully")
            return digest_text

        except Exception as e:
            logger.error("Error generating digest: %s", e)
            return None

    def send_email(self, digest, topics):
        """Send the digest via email using Resend."""
        if not self.resend_key or not self.email_from or not self.email_to:
            logger.warning("Email not configured. Skipping email send.")
            return False

        try:
            import resend
            resend.api_key = self.resend_key

            # Convert markdown to HTML for better email formatting
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
                    h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
                    h2 {{ color: #34495e; margin-top: 30px; }}
                    h3 {{ color: #555; }}
                    a {{ color: #3498db; text-decoration: none; }}
                    a:hover {{ text-decoration: underline; }}
                    ul {{ padding-left: 20px; }}
                    .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.9em; color: #777; }}
                </style>
            </head>
            <body>
                <h1>Daily News Digest - {datetime.now().strftime('%B %d, %Y')}</h1>
                <p><strong>Topics:</strong> {', '.join(topics)}</p>
                <hr>
                <div>{self._markdown_to_html(digest)}</div>
                <div class="footer">
                    <p>Generated by your AI News Digest Agent</p>
                    <p>Powered by Claude (Anthropic) and Brave Search</p>
                </div>
            </body>
            </html>
            """

            subject = f"Daily News Digest - {', '.join(topics)[:50]}{'...' if len(', '.join(topics)) > 50 else ''}"

            params = {
                "from": self.email_from,
                "to": [self.email_to],
                "subject": subject,
                "html": html_content
            }

            response = resend.Emails.send(params)
            logger.info("Email sent successfully! (ID: %s)", response['id'])
            return True

        except Exception as e:
            logger.error("Error sending email: %s", e)
            return False

    def _markdown_to_html(self, markdown_text):
        """Simple markdown to HTML conversion for email."""
        html = markdown_text

        # Convert headers (must do in reverse order to avoid conflicts)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Convert bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

        # Convert links
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)

        # Convert line breaks
        html = html.replace('\n\n', '<br><br>')
        html = html.replace('\n', '<br>')

        return html

    def create_digest(self, topics, articles_per_topic=5):
        """Create a news digest for the given topics."""
        logger.info("Creating digest for topics: %s", ', '.join(topics))

        # Collect articles for each topic
        topics_with_articles = {}

        for topic in topics:
            articles = self.search_news(topic, num_results=articles_per_topic)
            topics_with_articles[topic] = articles

        # Generate the digest
        digest = self.generate_digest(topics_with_articles)

        if digest:
            print(f"\n{'='*60}")
            print(f"YOUR DAILY NEWS DIGEST")
            print(f"{'='*60}\n")
            print(digest)
            print(f"\n{'='*60}\n")

            # Save to file in news folder
            news_folder = Settings.NEWS_FOLDER
            os.makedirs(news_folder, exist_ok=True)

            # Create filename with date and topics
            date_str = datetime.now().strftime('%Y%m%d')
            topics_str = "-".join([t.replace(" ", "_") for t in topics])
            filename = f"{news_folder}/news-digest-{date_str}-{topics_str}.md"

            try:
                with open(filename, 'w') as f:
                    f.write(f"# Daily News Digest - {datetime.now().strftime('%B %d, %Y')}\n\n")
                    f.write(digest)
                logger.info("Digest saved to: %s", filename)
            except Exception as e:
                logger.error("Could not save file: %s", e)

            # Send email
            self.send_email(digest, topics)

            return digest
        else:
            logger.error("Failed to generate digest")
            return None


def main():
    """Main function to run the news digest agent."""
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    print("""
Daily News Digest Agent
Powered by Claude + Brave Search
""")

    try:
        agent = NewsDigestAgent()

        # Check if topics provided as command-line arguments
        if len(sys.argv) > 1:
            # Topics provided via command line
            topics = [topic.strip() for topic in sys.argv[1:]]
            print(f"\nCreating digest for: {', '.join(topics)}")
        else:
            # Interactive mode - ask user
            print("What topics do you want in your news digest?")
            print("Enter topics separated by commas (e.g., AI, climate change, SpaceX)")
            print()

            topics_input = input("Topics: ").strip()

            if not topics_input:
                print("No topics provided. Using defaults...")
                topics = ["Artificial Intelligence", "Technology", "Science"]
            else:
                topics = [topic.strip() for topic in topics_input.split(",")]

            print(f"\nCreating digest for: {', '.join(topics)}")

        # Create the digest
        agent.create_digest(topics)

    except Exception as e:
        logger.error("Error: %s", e)


if __name__ == "__main__":
    main()
