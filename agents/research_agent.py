#!/usr/bin/env python3
"""
Simple AI Research Agent
A basic but functional agent that can search the web and answer questions.
"""

import json
import logging

from agents.base_agent import BaseAgent
from config.settings import Settings

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    def __init__(self, api_key=None):
        """Initialize the agent with an Anthropic API key."""
        super().__init__(api_key=api_key)

    def search_web(self, query):
        """Search the web using Brave Search API or mock results."""
        logger.info("Searching for: %s", query)

        brave_api_key = Settings.BRAVE_API_KEY

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
                logger.warning("Error with Brave API: %s", e)
                logger.info("Falling back to mock search")

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
        logger.info("Agent received: %s", user_message)

        # Add user message to history
        self.add_to_history("user", user_message)

        tools = [
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
        ]

        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.debug("Iteration %d", iteration)

            # Call Claude with tool definitions
            response = self.call_claude(
                messages=self.conversation_history,
                tools=tools
            )

            logger.debug("Stop reason: %s", response.stop_reason)

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

                        logger.info("Using tool: %s", tool_name)
                        logger.debug("Tool input: %s", json.dumps(tool_input, indent=2))

                        # Execute the tool
                        result = self.execute_tool(tool_name, tool_input)

                        logger.debug("Tool result: %s...", json.dumps(result, indent=2)[:200])

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

                logger.info("Final answer generated")
                return final_answer

            else:
                # Unexpected stop reason
                logger.warning("Unexpected stop reason: %s", response.stop_reason)
                break

        logger.warning("Max iterations (%d) reached", max_iterations)
        return "I apologize, but I've reached my maximum thinking iterations. Please try rephrasing your question."

    def chat(self):
        """Interactive chat mode."""
        print("\n" + "="*60)
        print("Research Agent - Interactive Mode")
        print("="*60)
        print("Type 'quit' or 'exit' to stop")
        print("Type 'clear' to clear conversation history")
        print("="*60 + "\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if user_input.lower() in ['quit', 'exit']:
                    print("Goodbye!")
                    break

                if user_input.lower() == 'clear':
                    self.conversation_history = []
                    print("Conversation history cleared\n")
                    continue

                if not user_input:
                    continue

                answer = self.run(user_input)
                print(f"\n{'='*60}")
                print(answer)
                print(f"{'='*60}\n")

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                logger.error("Error: %s", e)
                print(f"Error: {e}")


def main():
    """Main function to run the agent."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    print("""
Research Agent
Built with Claude by Anthropic

This agent can:
  - Answer questions using its knowledge
  - Search the web for current information
  - Maintain conversation context
""")

    # Create and run the agent
    try:
        agent = ResearchAgent()

        # You can either use chat mode or run single queries
        mode = input("\nChoose mode:\n  1. Interactive chat\n  2. Single query\nEnter 1 or 2: ").strip()

        if mode == "1":
            agent.chat()
        else:
            query = input("\nWhat would you like to know? ")
            if query:
                answer = agent.run(query)
                print(f"\n{'='*60}")
                print(answer)
                print(f"{'='*60}\n")

    except Exception as e:
        logger.error("Error initializing agent: %s", e)


if __name__ == "__main__":
    main()
