"""
Pending actions manager for whitelist modifications requiring confirmation.

Stores pending whitelist changes that need admin confirmation before execution.
"""

import json
import logging
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class PendingAction:
    """
    Represents a pending whitelist action awaiting confirmation.

    Attributes:
        action_id: Unique identifier for this action
        action_type: Type of action (add_teach, remove_teach, add_query, remove_query)
        email_to_modify: Email address or domain being added/removed
        requested_by: Email of admin who requested the action
        requested_at: ISO timestamp when action was requested
        expires_at: ISO timestamp when action expires
        confirmed: Whether action has been confirmed
    """

    action_id: str
    action_type: str  # add_teach, remove_teach, add_query, remove_query
    email_to_modify: str
    requested_by: str
    requested_at: str
    expires_at: str
    confirmed: bool = False


class PendingActionManager:
    """
    Manages pending whitelist actions requiring confirmation.

    Stores actions in a JSON file and provides methods for creating,
    confirming, and cleaning up expired actions.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the pending action manager.

        Args:
            storage_path: Path to JSON file for storing pending actions
        """
        self.storage_path = storage_path or Path("data/pending_whitelist_actions.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_storage_exists()
        logger.info(f"PendingActionManager initialized: {self.storage_path}")

    def _ensure_storage_exists(self):
        """Create storage file if it doesn't exist."""
        if not self.storage_path.exists():
            self._save_actions([])

    def _load_actions(self) -> List[PendingAction]:
        """
        Load pending actions from storage.

        Returns:
            List of PendingAction objects
        """
        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
                return [PendingAction(**item) for item in data]
        except Exception as e:
            logger.error(f"Error loading pending actions: {e}")
            return []

    def _save_actions(self, actions: List[PendingAction]):
        """
        Save pending actions to storage.

        Args:
            actions: List of PendingAction objects to save
        """
        try:
            with open(self.storage_path, "w") as f:
                json.dump([asdict(action) for action in actions], f, indent=2)
        except Exception as e:
            logger.error(f"Error saving pending actions: {e}")

    def create_pending_action(
        self,
        action_type: str,
        email_to_modify: str,
        requested_by: str,
        expiry_minutes: int = 30,
    ) -> PendingAction:
        """
        Create a new pending action requiring confirmation.

        Args:
            action_type: Type of action (add_teach, remove_teach, add_query, remove_query)
            email_to_modify: Email address or domain to modify
            requested_by: Email of admin requesting the action
            expiry_minutes: Minutes until action expires (default: 30)

        Returns:
            Created PendingAction object
        """
        # Generate unique action ID
        action_id = secrets.token_urlsafe(16)

        # Calculate expiry time
        now = datetime.now()
        expires_at = now + timedelta(minutes=expiry_minutes)

        # Create action
        action = PendingAction(
            action_id=action_id,
            action_type=action_type,
            email_to_modify=email_to_modify,
            requested_by=requested_by,
            requested_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            confirmed=False,
        )

        # Save to storage
        actions = self._load_actions()
        actions.append(action)
        self._save_actions(actions)

        logger.info(
            f"Created pending action {action_id}: {action_type} for {email_to_modify} "
            f"requested by {requested_by}"
        )

        return action

    def get_pending_action(self, action_id: str) -> Optional[PendingAction]:
        """
        Get a pending action by ID.

        Args:
            action_id: Unique action identifier

        Returns:
            PendingAction if found and not expired, None otherwise
        """
        actions = self._load_actions()

        for action in actions:
            if action.action_id == action_id:
                # Check if expired
                expires_at = datetime.fromisoformat(action.expires_at)
                if datetime.now() > expires_at:
                    logger.warning(f"Action {action_id} has expired")
                    return None

                return action

        return None

    def confirm_action(self, action_id: str) -> bool:
        """
        Confirm and mark an action as ready for execution.

        Args:
            action_id: Unique action identifier

        Returns:
            True if confirmed successfully, False otherwise
        """
        actions = self._load_actions()

        for action in actions:
            if action.action_id == action_id:
                # Check if expired
                expires_at = datetime.fromisoformat(action.expires_at)
                if datetime.now() > expires_at:
                    logger.warning(f"Cannot confirm expired action {action_id}")
                    return False

                # Mark as confirmed
                action.confirmed = True
                self._save_actions(actions)

                logger.info(f"Confirmed action {action_id}")
                return True

        logger.warning(f"Action {action_id} not found")
        return False

    def remove_action(self, action_id: str):
        """
        Remove an action from storage (after execution or expiry).

        Args:
            action_id: Unique action identifier
        """
        actions = self._load_actions()
        actions = [a for a in actions if a.action_id != action_id]
        self._save_actions(actions)
        logger.info(f"Removed action {action_id}")

    def cleanup_expired(self) -> int:
        """
        Remove all expired actions from storage.

        Returns:
            Number of actions removed
        """
        actions = self._load_actions()
        now = datetime.now()

        valid_actions = []
        expired_count = 0

        for action in actions:
            expires_at = datetime.fromisoformat(action.expires_at)
            if now <= expires_at:
                valid_actions.append(action)
            else:
                expired_count += 1
                logger.info(f"Removing expired action {action.action_id}")

        if expired_count > 0:
            self._save_actions(valid_actions)
            logger.info(f"Cleaned up {expired_count} expired actions")

        return expired_count

    def get_pending_actions_for_user(self, user_email: str) -> List[PendingAction]:
        """
        Get all pending actions requested by a specific user.

        Args:
            user_email: Email of the requesting user

        Returns:
            List of pending actions for this user
        """
        actions = self._load_actions()
        user_actions = []

        for action in actions:
            if action.requested_by.lower() == user_email.lower():
                # Check if expired
                expires_at = datetime.fromisoformat(action.expires_at)
                if datetime.now() <= expires_at:
                    user_actions.append(action)

        return user_actions


# Global instance
_pending_action_manager = None


def get_pending_action_manager() -> PendingActionManager:
    """
    Get the global PendingActionManager instance.

    Returns:
        PendingActionManager singleton
    """
    global _pending_action_manager
    if _pending_action_manager is None:
        _pending_action_manager = PendingActionManager()
    return _pending_action_manager
