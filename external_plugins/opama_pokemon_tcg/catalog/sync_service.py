"""
Catalog Sync Service

Orchestrates synchronization of Pokemon TCG card data from the API to the database.
Handles:
- Discovery of new sets
- Fetching cards from the API
- Importing/updating cards in database
- Tracking sync status

Usage:
    from sqlmodel import Session
    from opama_pokemon_tcg.catalog.sync_service import CatalogSyncService

    with Session(engine) as session:
        service = CatalogSyncService(session)
        new_sets = service.discover_new_sets()
        for set_id in new_sets:
            service.sync_set(set_id)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlmodel import Session, select

from opama_pokemon_tcg.catalog.pokemon_tcg_client import PokemonTCGClient
from opama_pokemon_tcg.catalog.models import Card, Set, CatalogSyncLog, SetSyncStatus


class CatalogSyncService:
    """
    Service for synchronizing Pokemon TCG catalog data.

    This service acts as the coordinator between the Pokemon TCG API client
    and the database, handling the business logic for syncing sets and cards.
    """

    def __init__(
        self,
        session: Session,
        api_key: Optional[str] = None,
        rate_limit_delay: float = 1.0
    ):
        """
        Initialize the catalog sync service.

        Args:
            session: SQLModel database session
            api_key: Optional Pokemon TCG API key
            rate_limit_delay: Seconds between API requests (default: 1.0)
        """
        self.session = session
        self.client = PokemonTCGClient(
            api_key=api_key,
            rate_limit_delay=rate_limit_delay
        )

    def discover_new_sets(self) -> List[str]:
        """
        Discover sets that exist in the API but not in the database.

        Returns:
            List of set IDs (e.g., ['me1', 'me2']) that need to be synced

        Example:
            >>> service = CatalogSyncService(session)
            >>> new_sets = service.discover_new_sets()
            >>> print(f"Found {len(new_sets)} new sets")
        """
        # Get all sets from API
        api_sets = self.client.list_all_sets()

        # Get existing set IDs from database
        local_set_ids = set(self.session.exec(select(Set.id)).all())

        # Find sets that are in API but not in database
        new_set_ids = [
            s["id"] for s in api_sets
            if s["id"] not in local_set_ids
        ]

        return new_set_ids

    def sync_set(self, set_id: str) -> bool:
        """
        Sync a single set: fetch cards from API and import to database.

        This method:
        1. Gets set info from API
        2. Creates/updates Set record
        3. Fetches all cards for the set
        4. Creates/updates Card records
        5. Updates SetSyncStatus

        Args:
            set_id: Pokemon TCG set ID (e.g., "me1")

        Returns:
            True if sync succeeded, False otherwise

        Example:
            >>> service = CatalogSyncService(session)
            >>> success = service.sync_set("me1")
            >>> if success:
            ...     print("Sync successful")
        """
        try:
            # 1. Get set info
            set_info = self.client.get_set_info(set_id)
            if not set_info:
                raise ValueError(f"Set {set_id} not found in API")

            # 2. Create or update Set record
            db_set = self.session.get(Set, set_id)
            if not db_set:
                db_set = Set(
                    id=set_id,
                    name=set_info.get("name", ""),
                    series=set_info.get("series", ""),
                    release_date=set_info.get("releaseDate"),
                    total=set_info.get("total", 0),
                    printed_total=set_info.get("printedTotal", 0),
                )
                self.session.add(db_set)
            else:
                # Update existing set
                db_set.name = set_info.get("name", db_set.name)
                db_set.series = set_info.get("series", db_set.series)
                db_set.release_date = set_info.get("releaseDate", db_set.release_date)
                db_set.total = set_info.get("total", db_set.total)
                db_set.printed_total = set_info.get("printedTotal", db_set.printed_total)
                self.session.add(db_set)

            self.session.commit()

            # 3. Fetch cards from API
            api_cards = self.client.fetch_set_cards(set_id)

            # 4. Import cards
            cards_added = 0
            cards_updated = 0

            for api_card in api_cards:
                card_id = api_card.get("id")
                if not card_id:
                    continue

                # Check if card exists
                db_card = self.session.get(Card, card_id)

                if not db_card:
                    # Create new card
                    db_card = self._api_card_to_model(api_card, set_id)
                    self.session.add(db_card)
                    cards_added += 1
                else:
                    # Update existing card
                    self._update_card_from_api(db_card, api_card)
                    cards_updated += 1

            # Commit all cards
            self.session.commit()

            # 5. Update SetSyncStatus
            sync_status = self.session.get(SetSyncStatus, set_id)
            if not sync_status:
                sync_status = SetSyncStatus(set_id=set_id)

            sync_status.last_synced_at = datetime.utcnow()
            sync_status.cards_count = len(api_cards)
            sync_status.sync_status = "success"
            sync_status.error_details = None

            self.session.add(sync_status)
            self.session.commit()

            print(f"✓ Synced {set_id}: +{cards_added} new, ~{cards_updated} updated")
            return True

        except Exception as e:
            # Rollback transaction on error
            self.session.rollback()

            # Update SetSyncStatus to track failure
            sync_status = self.session.get(SetSyncStatus, set_id)
            if not sync_status:
                sync_status = SetSyncStatus(set_id=set_id)

            sync_status.last_synced_at = datetime.utcnow()
            sync_status.sync_status = "failed"
            sync_status.error_details = str(e)

            self.session.add(sync_status)
            self.session.commit()

            print(f"✗ Failed to sync {set_id}: {e}")
            return False

    def create_sync_log(self, sync_type: str = "scheduled") -> CatalogSyncLog:
        """
        Create a new sync log entry.

        Args:
            sync_type: Type of sync ('scheduled', 'manual', 'initial')

        Returns:
            New CatalogSyncLog instance (not yet committed)

        Example:
            >>> service = CatalogSyncService(session)
            >>> log = service.create_sync_log("manual")
            >>> # ... perform sync ...
            >>> service.finalize_sync_log(log, "success")
        """
        log = CatalogSyncLog(
            sync_type=sync_type,
            started_at=datetime.utcnow(),
            status="running"
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        return log

    def finalize_sync_log(
        self,
        log: CatalogSyncLog,
        status: str,
        error_message: Optional[str] = None
    ):
        """
        Update and finalize a sync log.

        Args:
            log: CatalogSyncLog instance to update
            status: Final status ('success', 'partial', 'failed')
            error_message: Optional error message if sync failed
        """
        log.completed_at = datetime.utcnow()
        log.status = status
        if error_message:
            log.error_message = error_message

        self.session.add(log)
        self.session.commit()

    def _api_card_to_model(self, api_card: Dict, set_id: str) -> Card:
        """
        Convert an API card response to a Card model.

        Args:
            api_card: Card data from Pokemon TCG API
            set_id: Set ID for this card

        Returns:
            Card model instance (not yet added to session)
        """
        # Extract nested fields
        set_data = api_card.get("set", {})
        images = api_card.get("images", {})
        legalities = api_card.get("legalities", {})
        tcgplayer = api_card.get("tcgplayer", {})

        # Create card with all fields
        card = Card(
            id=api_card.get("id"),
            name=api_card.get("name", ""),
            set_id=set_id,
            number=api_card.get("number"),
            rarity=api_card.get("rarity"),
            supertype=api_card.get("supertype"),
            subtypes=",".join(api_card.get("subtypes", [])),
            types=",".join(api_card.get("types", [])),
            hp=self._safe_int(api_card.get("hp")),
            evolves_from=api_card.get("evolvesFrom"),
            regulation_mark=api_card.get("regulationMark"),
            illustrator=api_card.get("artist"),
            # Abilities (take first one)
            ability_name=self._get_first_ability_field(api_card, "name"),
            ability_text=self._get_first_ability_field(api_card, "text"),
            ability_type=self._get_first_ability_field(api_card, "type"),
            # Attacks (take first 3)
            attack1_name=self._get_attack_field(api_card, 0, "name"),
            attack1_cost=self._get_attack_cost(api_card, 0),
            attack1_damage=self._get_attack_field(api_card, 0, "damage"),
            attack1_text=self._get_attack_field(api_card, 0, "text"),
            attack2_name=self._get_attack_field(api_card, 1, "name"),
            attack2_cost=self._get_attack_cost(api_card, 1),
            attack2_damage=self._get_attack_field(api_card, 1, "damage"),
            attack2_text=self._get_attack_field(api_card, 1, "text"),
            attack3_name=self._get_attack_field(api_card, 2, "name"),
            attack3_cost=self._get_attack_cost(api_card, 2),
            attack3_damage=self._get_attack_field(api_card, 2, "damage"),
            attack3_text=self._get_attack_field(api_card, 2, "text"),
            # Weaknesses/Resistances
            weaknesses=self._format_type_modifiers(api_card.get("weaknesses", [])),
            resistances=self._format_type_modifiers(api_card.get("resistances", [])),
            retreat_cost=len(api_card.get("retreatCost", [])),
            # Other fields
            rules_text=" | ".join(api_card.get("rules", [])) or None,
            flavor_text=api_card.get("flavorText"),
            legal_standard=legalities.get("standard"),
            legal_expanded=legalities.get("expanded"),
            legal_unlimited=legalities.get("unlimited"),
            national_pokedex_numbers=",".join(
                str(n) for n in api_card.get("nationalPokedexNumbers", [])
            ) or None,
            release_date=set_data.get("releaseDate") or api_card.get("releaseDate"),
            tcgplayer_product_id=str(tcgplayer.get("productId")) if tcgplayer.get("productId") else None,
            image_small=images.get("small"),
            image_large=images.get("large"),
        )

        # Calculate number_sort
        if card.number:
            digits = "".join(ch for ch in str(card.number) if ch.isdigit())
            if digits:
                card.number_sort = int(digits)

        return card

    def _update_card_from_api(self, card: Card, api_card: Dict):
        """
        Update an existing card with data from the API.

        Args:
            card: Existing Card model to update
            api_card: Card data from API
        """
        # Update fields (could be more selective if needed)
        updated_card = self._api_card_to_model(api_card, card.set_id)

        # Copy non-ID fields
        for field in Card.__fields__:
            if field != "id":
                setattr(card, field, getattr(updated_card, field))

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """Safely convert value to int, return None if not possible."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _get_first_ability_field(api_card: Dict, field: str) -> Optional[str]:
        """Get a field from the first ability."""
        abilities = api_card.get("abilities", [])
        if abilities and isinstance(abilities, list) and len(abilities) > 0:
            return abilities[0].get(field)
        return None

    @staticmethod
    def _get_attack_field(api_card: Dict, index: int, field: str) -> Optional[str]:
        """Get a field from a specific attack."""
        attacks = api_card.get("attacks", [])
        if attacks and isinstance(attacks, list) and len(attacks) > index:
            return attacks[index].get(field)
        return None

    @staticmethod
    def _get_attack_cost(api_card: Dict, index: int) -> Optional[str]:
        """Get formatted cost for a specific attack."""
        attacks = api_card.get("attacks", [])
        if attacks and isinstance(attacks, list) and len(attacks) > index:
            cost = attacks[index].get("cost", [])
            return ",".join(cost) if cost else None
        return None

    @staticmethod
    def _format_type_modifiers(modifiers: List[Dict]) -> Optional[str]:
        """Format weaknesses or resistances as string."""
        if not modifiers:
            return None
        formatted = [
            f"{m.get('type')}:{m.get('value')}"
            for m in modifiers
            if m.get('type') and m.get('value')
        ]
        return ";".join(formatted) if formatted else None
