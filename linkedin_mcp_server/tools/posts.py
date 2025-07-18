import json
import logging
import os
from datetime import datetime
from typing import List

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP

logger = logging.getLogger(__name__)
load_dotenv()

DATA_FILE = "linkedin_posts.json"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")


def register_posts_tools(mcp: FastMCP):
    """
    Register all post-related tools with the MCP server.
    """

    @mcp.tool()
    def fetch_and_save_linkedin_posts(username: str) -> str:
        """
        Fetch LinkedIn posts for a given username using the Fresh-LinkedIn-Profile-Data API and save them to a local JSON file.

        Args:
            username (str): The LinkedIn username (e.g., "anistji").

        Returns:
            str: A message indicating the result of the operation.
        """
        if not RAPIDAPI_KEY:
            return "Error: RAPIDAPI_KEY is not set in the environment variables."

        url = "https://fresh-linkedin-profile-data.p.rapidapi.com/get-profile-posts"
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "fresh-linkedin-profile-data.p.rapidapi.com",
        }
        querystring = {"linkedin_url": f"https://www.linkedin.com/in/{username}/", "type": "posts"}

        try:
            response = requests.get(url, headers=headers, params=querystring)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return f"Error fetching posts: {e}"

        data = response.json()
        posts = []
        for post in data.get("data", []):
            posts.append(
                {
                    "Post URL": post.get("post_url", ""),
                    "Text": post.get("text", ""),
                    "Like Count": post.get("num_likes", 0),
                    "Total Reactions": post.get("num_reactions", 0),
                    "Posted Date": post.get("posted", "").split(" ")[0],
                    "Author Name": f"{post.get('poster', {}).get('first', '')} {post.get('poster', {}).get('last', '')}",
                    "Author Profile": post.get("poster_linkedin_url", ""),
                    "Author Headline": post.get("poster", {}).get("headline", ""),
                    "Main Image": post.get("images", [{}])[0].get("url", "") if post.get("images") else "",
                    "All Images": ", ".join([img.get("url", "") for img in post.get("images", [])]),
                    "reshared": post.get("reshared", False),
                    "Comment Count": post.get("num_comments", 0),
                }
            )

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=4)

        return f"Successfully fetched and saved {len(posts)} posts to {DATA_FILE}"

    @mcp.tool()
    def get_saved_posts(start: int = 0, limit: int = 5) -> dict:
        """
        Retrieve saved LinkedIn posts from the local JSON file with pagination.

        Args:
            start (int): Index of the first post to retrieve.
            limit (int): Number of posts to return (Max: 5).

        Returns:
            dict: Contains retrieved posts and metadata about the result.
        """
        if not os.path.exists(DATA_FILE):
            return {"message": "No data found. Fetch posts first using fetch_and_save_linkedin_posts().", "posts": []}

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                posts = json.load(f)

            total_posts = len(posts)
            limit = min(limit, 5)
            paginated_posts = posts[start : start + limit]

            return {"posts": paginated_posts, "total_posts": total_posts, "has_more": start + limit < total_posts}
        except json.JSONDecodeError:
            return {"message": "Error reading data file. JSON might be corrupted.", "posts": []}

    @mcp.tool()
    def search_posts(keywords: List[str], mode: str = "OR") -> dict:
        """
        Search saved LinkedIn posts for specific keywords.

        Args:
            keywords (List[str]): A list of keywords to search for.
            mode (str): The search mode. "OR" for any keyword, "AND" for all keywords.

        Returns:
            dict: A dictionary containing the search results and metadata.
        """
        if not os.path.exists(DATA_FILE):
            return {"message": "No data found. Fetch posts first.", "posts": []}

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            posts = json.load(f)

        filtered_posts = []
        for post in posts:
            text = post.get("Text", "").lower()
            if mode.upper() == "AND":
                if all(keyword.lower() in text for keyword in keywords):
                    filtered_posts.append(post)
            else:  # OR mode
                if any(keyword.lower() in text for keyword in keywords):
                    filtered_posts.append(post)

        return {
            "keywords": keywords,
            "mode": mode,
            "total_results": len(filtered_posts),
            "posts": filtered_posts[:5],
            "has_more": len(filtered_posts) > 5,
        }

    @mcp.tool()
    def get_top_posts(metric: str = "Like Count", top_n: int = 5) -> dict:
        """
        Get the top LinkedIn posts from the local file based on an engagement metric.

        Args:
            metric (str): The metric to rank posts by ("Like Count", "Total Reactions").
            top_n (int): Number of top posts to return.

        Returns:
            dict: A list of top posts sorted by the selected metric.
        """
        if not os.path.exists(DATA_FILE):
            return {"message": "No data found. Fetch posts first.", "posts": []}

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            posts = json.load(f)

        if metric not in ["Like Count", "Total Reactions"]:
            return {"message": "Invalid metric. Use 'Like Count' or 'Total Reactions'."}

        sorted_posts = sorted(posts, key=lambda x: x.get(metric, 0), reverse=True)

        return {"metric": metric, "posts": sorted_posts[:top_n]}

    @mcp.tool()
    def get_posts_by_date(start_date: str, end_date: str) -> dict:
        """
        Retrieve posts from the local file within a specified date range.

        Args:
            start_date (str): Start date in 'YYYY-MM-DD' format.
            end_date (str): End date in 'YYYY-MM-DD' format.

        Returns:
            dict: A list of posts within the date range.
        """
        if not os.path.exists(DATA_FILE):
            return {"message": "No data found. Fetch posts first.", "posts": []}

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            posts = json.load(f)

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return {"message": "Invalid date format. Use 'YYYY-MM-DD'."}

        filtered_posts = [post for post in posts if start_dt <= datetime.strptime(post["Posted Date"], "%Y-%m-%d") <= end_dt]

        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_results": len(filtered_posts),
            "posts": filtered_posts,
        }
