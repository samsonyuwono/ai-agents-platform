#!/usr/bin/env env python3
"""
Simple AI Research Agent
A basic but functional agent that can search the web and answer questions.
"""

import anthropic
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class ResearchAgent:
    def __init__(self, api_key=None):
        """Initialize the agent with an Anthropic API key."""
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Please set ANTHROPIC_API_KEY environment variable or pass api_key")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.conversation_history = []
        self.model = "claude-sonnet-4-20250514"

    def add_to_history(self, role, content):
        """Add a message to conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content
        })

    def search_web(self, query):
        """Search the web using Brave Search API or mock results."""
        print(f"  🔍 Searching for: {query}")

        # Check if Brave API key is available
        brave_api_key = os.environ.get("BRAVE_API_KEY")

        if brave_api_key:
            # Use Brave Search API
            try:
                import requests
                url = "https://api.search.brave.com/res/v1/web/search"
                headers = {
                    "Accept": "application/json",
                    "X-Subscription-Token": brave_api_key
                }
                params = {
                    "q": query,
                    "count": 5  # Number of results
                }

                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                # Format results
                results = []
                for item in data.get("web", {}).get("results", [])[:5]:
                    results.append({
                        "title": item.get("title"),
                        "snippet": item.get("description"),
                        "url": item.get("url")
                    })

                return {
                    "query": query,
                    "results": results,
                    "source": "Brave Search API"
                }
            except Exception as e:
                print(f"  ⚠️  Error with Brave API: {e}")
                print(f"  📝 Falling back to mock search")

        # Fall back to mock results if no API key or error
        return {
            "query": query,
            "results": [
                {
                    "title": "Example Result",
                    "snippet": "This is a simulated search result. Add BRAVE_API_KEY to .env to use real search.",
                    "url": "https://example.com"
                }
            ],
            "note": "Mock search - add Brave API key to .env for real search"
        }

    def execute_tool(self, tool_name, tool_input):
        """Execute a tool based on the tool name."""
        if tool_name == "web_search":
            return self.search_web(tool_input["query"])
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def run(self, user_message, max_iterations=5):
        """
        Run the agent with a user message.
        The agent will loop until it provides a final answer or hits max iterations.
        """
        print(f"\n{'='*60}")
        print(f"🤖 Agent received: {user_message}")
        print(f"{'='*60}\n")

        # Add user message to history
        self.add_to_history("user", user_message)

        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            print(f"--- Iteration {iteration} ---")

            # Call Claude with tool definitions
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=[
                    {
                        "name": "web_search",
                        "description": "Search the web for current information. Use this when you need up-to-date information or facts you don't know.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to look up"
                                }
                            },
                            "required": ["query"]
                        }
                    }
                ],
                messages=self.conversation_history
            )

            print(f"  Stop reason: {response.stop_reason}")

            # Check if Claude wants to use a tool
            if response.stop_reason == "tool_use":
                # Add Claude's response to history
                self.add_to_history("assistant", response.content)

                # Execute all tool calls
                tool_results = []
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_name = content_block.name
                        tool_input = content_block.input
                        tool_use_id = content_block.id

                        print(f"  🔧 Using tool: {tool_name}")
                        print(f"     Input: {json.dumps(tool_input, indent=2)}")

                        # Execute the tool
                        result = self.execute_tool(tool_name, tool_input)

                        print(f"     Result: {json.dumps(result, indent=2)[:200]}...")

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(result)
                        })

                # Add tool results to history
                self.add_to_history("user", tool_results)

            elif response.stop_reason == "end_turn":
                # Claude is done and provided a final answer
                self.add_to_history("assistant", response.content)

                # Extract text from response
                final_answer = ""
                for content_block in response.content:
                    if hasattr(content_block, "text"):
                        final_answer += content_block.text

                print(f"\n{'='*60}")
                print(f"✅ Final Answer:")
                print(f"{'='*60}")
                print(final_answer)
                print(f"{'='*60}\n")

                return final_answer

            else:
                # Unexpected stop reason
                print(f"⚠️  Unexpected stop reason: {response.stop_reason}")
                break

        print(f"⚠️  Max iterations ({max_iterations}) reached")
        return "I apologize, but I've reached my maximum thinking iterations. Please try rephrasing your question."

    def chat(self):
        """Interactive chat mode."""
        print("\n" + "="*60)
        print("🤖 Research Agent - Interactive Mode")
        print("="*60)
        print("Type 'quit' or 'exit' to stop")
        print("Type 'clear' to clear conversation history")
        print("="*60 + "\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if user_input.lower() in ['quit', 'exit']:
                    print("👋 Goodbye!")
                    break

                if user_input.lower() == 'clear':
                    self.conversation_history = []
                    print("🗑️  Conversation history cleared\n")
                    continue

                if not user_input:
                    continue

                self.run(user_input)

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")


def main():
    """Main function to run the agent."""
    print("""
╔══════════════════════════════════════════════════════════╗
║           Simple AI Research Agent                       ║
║           Built with Claude by Anthropic                 ║
╚══════════════════════════════════════════════════════════╝

This agent can:
  • Answer questions using its knowledge
  • Search the web for current information (mocked for demo)
  • Maintain conversation context

To make web search real, integrate a search API like:
  - Google Custom Search API
  - Brave Search API
  - Bing Search API
""")

    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY not found in environment variables")
        api_key = input("Enter your Anthropic API key (or press Enter to quit): ").strip()
        if not api_key:
            print("No API key provided. Exiting.")
            return

    # Create and run the agent
    try:
        agent = ResearchAgent(api_key=api_key)

        # You can either use chat mode or run single queries
        mode = input("\nChoose mode:\n  1. Interactive chat\n  2. Single query\nEnter 1 or 2: ").strip()

        if mode == "1":
            agent.chat()
        else:
            query = input("\nWhat would you like to know? ")
            if query:
                agent.run(query)

    except Exception as e:
        print(f"❌ Error initializing agent: {e}")


if __name__ == "__main__":
    main()
