import logging
import time
from typing import Any, Dict, List

from fastmcp import FastMCP
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from linkedin_mcp_server.error_handler import handle_tool_error, safe_get_driver

logger = logging.getLogger(__name__)

# --- Constants ---
MAX_COMMENTS = 20
MAX_REACTIONS = 20


def _scroll_for_items(driver: WebDriver, max_items: int):
    """Scroll down until max_items are loaded or the page ends."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        items = driver.find_elements(By.CSS_SELECTOR, "div.feed-shared-update-v2")
        if len(items) >= max_items:
            break

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def _scrape_comments(driver: WebDriver) -> List[Dict[str, str]]:
    """Scrape comments from the current page, handling both direct comments and replies."""
    comments = []
    try:
        comment_list = driver.find_element(By.CSS_SELECTOR, "div.scaffold-finite-scroll__content")
        for item in comment_list.find_elements(By.CSS_SELECTOR, "div.feed-shared-update-v2"):
            if len(comments) >= MAX_COMMENTS:
                break

            try:
                is_reply = "replied to" in item.find_element(By.CSS_SELECTOR, "span.update-components-header__text-view").text
            except Exception:
                is_reply = False

            try:
                post_author = item.find_element(By.CSS_SELECTOR, "span.update-components-actor__title").text
                post_content_elements = item.find_elements(By.CSS_SELECTOR, "div.update-components-text")
                post_content = post_content_elements[0].text if post_content_elements else ""

                comment_data = {
                    "post_author": post_author,
                    "post_content": post_content,
                    "is_reply": is_reply,
                    "original_comment": None,
                }

                if is_reply:
                    reply_element = item.find_element(By.CSS_SELECTOR, "article.comments-comment-entity--reply")
                    comment_data["comment"] = reply_element.find_element(By.CSS_SELECTOR, "span.comments-comment-item__main-content").text
                    comment_data["timestamp"] = reply_element.find_element(By.CSS_SELECTOR, "time.comments-comment-meta__data").text

                    original_comment_element = item.find_element(By.CSS_SELECTOR, "article.comments-comment-entity:not(.comments-comment-entity--reply)")
                    comment_data["original_comment"] = original_comment_element.find_element(By.CSS_SELECTOR, "span.comments-comment-item__main-content").text
                else:
                    comment_element = item.find_element(By.CSS_SELECTOR, "article.comments-comment-entity")
                    comment_data["comment"] = comment_element.find_element(By.CSS_SELECTOR, "span.comments-comment-item__main-content").text
                    comment_data["timestamp"] = comment_element.find_element(By.CSS_SELECTOR, "time.comments-comment-meta__data").text

                comments.append(comment_data)
            except Exception as e:
                logger.warning(f"Could not parse a comment/reply item for {post_author}: {e}")

    except Exception as e:
        logger.error(f"Error scraping comments list: {e}")
    return comments


def _scrape_reactions(driver: WebDriver) -> List[Dict[str, str]]:
    """Scrape reactions from the current page."""
    reactions = []
    try:
        reaction_list = driver.find_element(By.CSS_SELECTOR, "div.scaffold-finite-scroll__content")
        for item in reaction_list.find_elements(By.CSS_SELECTOR, "div.feed-shared-update-v2"):
            if len(reactions) >= MAX_REACTIONS:
                break
            try:
                post_author = item.find_element(By.CSS_SELECTOR, "span.update-components-actor__title").text
                post_content = item.find_element(By.CSS_SELECTOR, "div.update-components-text").text
                reaction_text = item.find_element(By.CSS_SELECTOR, "span.update-components-header__text-view").text
                timestamp = item.find_element(By.CSS_SELECTOR, "span.update-components-actor__sub-description").text
                reactions.append({
                    "post_author": post_author,
                    "post_content": post_content,
                    "reaction": reaction_text,
                    "timestamp": timestamp
                })
            except Exception:
                pass  # Ignore if a specific item fails
    except Exception as e:
        logger.error(f"Error scraping reactions list: {e}")
    return reactions


def register_activity_tools(mcp: FastMCP) -> None:
    """
    Register all activity-related tools with the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance
    """

    @mcp.tool()
    async def get_person_activity(linkedin_username: str) -> Dict[str, Any]:
        """
        Get a specific person's LinkedIn comments and reactions. This tool scrapes the user's activity page to return their recent comments and reactions, but does not include their posts.

        Args:
            linkedin_username (str): LinkedIn username (e.g., "stickerdaniel", "anistji")

        Returns:
            Dict[str, Any]: Structured data containing the person's comments and reactions.
        """
        try:
            driver = safe_get_driver()
            activities = {"comments": [], "reactions": []}

            # --- Scrape Comments ---
            print('linkedin_username', linkedin_username)
            try:
                comments_url = f"https://www.linkedin.com/in/{linkedin_username}/recent-activity/comments/"
                print('linkedin_comments_url', comments_url)
                driver.get(comments_url)
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.scaffold-finite-scroll__content"))
                )
                _scroll_for_items(driver, MAX_COMMENTS)
                activities["comments"] = _scrape_comments(driver)
            except TimeoutException:
                logger.warning(f"Timeout waiting for comments page for {linkedin_username}. The user may have no comments or the page is slow.")
            except Exception as e:
                logger.error(f"An unexpected error occurred while scraping comments: {e}")

            # --- Scrape Reactions ---
            try:
                reactions_url = f"https://www.linkedin.com/in/{linkedin_username}/recent-activity/reactions/"
                driver.get(reactions_url)
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.scaffold-finite-scroll__content"))
                )
                _scroll_for_items(driver, MAX_REACTIONS)
                activities["reactions"] = _scrape_reactions(driver)
            except TimeoutException:
                logger.warning(f"Timeout waiting for reactions page for {linkedin_username}. The user may have no reactions or the page is slow.")
            except Exception as e:
                logger.error(f"An unexpected error occurred while scraping reactions: {e}")

            return activities
        except Exception as e:
            return handle_tool_error(e, "get_person_activity")
