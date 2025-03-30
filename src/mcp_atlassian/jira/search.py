"""Module for Jira search operations."""

import logging

from ..models.jira import JiraIssue, JiraSearchResult
from .client import JiraClient
from .utils import parse_date_ymd

logger = logging.getLogger("mcp-jira")


class SearchMixin(JiraClient):
    """Mixin for Jira search operations."""

    def search_issues(
        self,
        jql: str,
        fields: str
        | list[str]
        | tuple[str, ...]
        | set[str]
        | None = "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
        projects_filter: str | None = None,
    ) -> list[JiraIssue]:
        """
        Search for issues using JQL (Jira Query Language).

        Args:
            jql: JQL query string
            fields: Fields to return (comma-separated string, list, tuple, set, or "*all")
            start: Starting index
            limit: Maximum issues to return
            expand: Optional items to expand (comma-separated)
            projects_filter: Optional comma-separated list of project keys to filter by, overrides config

        Returns:
            List of JiraIssue models representing the search results

        Raises:
            Exception: If there is an error searching for issues
        """
        try:
            # Use projects_filter parameter if provided, otherwise fall back to config
            filter_to_use = projects_filter or self.config.projects_filter

            # Apply projects filter if present
            if filter_to_use:
                # Split projects filter by commas and handle possible whitespace
                projects = [p.strip() for p in filter_to_use.split(",")]

                # Build the project filter query part
                if len(projects) == 1:
                    project_query = f"project = {projects[0]}"
                else:
                    quoted_projects = [f'"{p}"' for p in projects]
                    projects_list = ", ".join(quoted_projects)
                    project_query = f"project IN ({projects_list})"

                # Add the project filter to existing query
                if jql and project_query:
                    if "project = " not in jql and "project IN" not in jql:
                        # Only add if not already filtering by project
                        jql = f"({jql}) AND {project_query}"
                else:
                    jql = project_query

                logger.info(f"Applied projects filter to query: {jql}")

            # Convert fields to proper format if it's a list/tuple/set
            fields_param = fields
            if fields and isinstance(fields, list | tuple | set):
                fields_param = ",".join(fields)

            response = self.jira.jql(
                jql, fields=fields_param, start=start, limit=limit, expand=expand
            )

            # Convert the response to a search result model
            search_result = JiraSearchResult.from_api_response(
                response, base_url=self.config.url, requested_fields=fields
            )

            # Return the list of issues
            return search_result.issues
        except Exception as e:
            logger.error(f"Error searching issues with JQL '{jql}': {str(e)}")
            raise Exception(f"Error searching issues: {str(e)}") from e

    def get_project_issues(
        self, project_key: str, start: int = 0, limit: int = 50
    ) -> list[JiraIssue]:
        """
        Get all issues for a project.

        Args:
            project_key: The project key
            start: Starting index
            limit: Maximum results to return

        Returns:
            List of JiraIssue models containing project issues

        Raises:
            Exception: If there is an error getting project issues
        """
        jql = f"project = {project_key} ORDER BY created DESC"
        return self.search_issues(jql, start=start, limit=limit)

    def get_epic_issues(
        self, epic_key: str, start: int = 0, limit: int = 50
    ) -> list[JiraIssue]:
        """
        Get all issues linked to a specific epic.

        Args:
            epic_key: The key of the epic (e.g. 'PROJ-123')
            limit: Maximum number of issues to return

        Returns:
            List of JiraIssue models representing the issues linked to the epic

        Raises:
            ValueError: If the issue is not an Epic
            Exception: If there is an error getting epic issues
        """
        try:
            # First, check if the issue is an Epic
            epic = self.jira.issue(epic_key)
            fields_data = epic.get("fields", {})

            # Safely check if the issue is an Epic
            issue_type = None
            issuetype_data = fields_data.get("issuetype")
            if issuetype_data is not None:
                issue_type = issuetype_data.get("name", "")

            if issue_type != "Epic":
                error_msg = (
                    f"Issue {epic_key} is not an Epic, it is a "
                    f"{issue_type or 'unknown type'}"
                )
                raise ValueError(error_msg)

            # Try with 'issueFunction in issuesScopedToEpic'
            try:
                jql = f'issueFunction in issuesScopedToEpic("{epic_key}")'
                return self.search_issues(jql, start=start, limit=limit)
            except Exception as e:
                # Log exception but continue with fallback
                logger.warning(
                    f"Error searching epic issues with issueFunction: {str(e)}"
                )

            # Fallback to 'Epic Link' field
            jql = f"'Epic Link' = {epic_key}"
            return self.search_issues(jql, start=start, limit=limit)

        except ValueError:
            # Re-raise ValueError for non-epic issues
            raise
        except Exception as e:
            logger.error(f"Error getting issues for epic {epic_key}: {str(e)}")
            raise Exception(f"Error getting epic issues: {str(e)}") from e

    def _parse_date(self, date_str: str) -> str:
        """
        Parse a date string from ISO format to a more readable format.

        Args:
            date_str: Date string in ISO format

        Returns:
            Formatted date string
        """
        # Use the common utility function for consistent formatting
        return parse_date_ymd(date_str)
