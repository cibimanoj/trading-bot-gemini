from datetime import datetime, timezone
import pytz

class TimezoneNormalizer:
    IST = pytz.timezone("Asia/Kolkata")

    @classmethod
    def now_ist_aware(cls) -> datetime:
        """Returns the current aware datetime in IST."""
        return datetime.now(cls.IST)

    @classmethod
    def now_ist_naive(cls) -> datetime:
        """Returns the current naive datetime representing IST time (matches Kite SDK outputs)."""
        return cls.now_ist_aware().replace(tzinfo=None)
    
    @classmethod
    def utc_unix_now(cls) -> float:
        """Returns the current high-precision UTC UNIX timestamp for global API bridging."""
        return datetime.now(timezone.utc).timestamp()
    
    @classmethod
    def make_ist_aware(cls, dt: datetime) -> datetime:
        """Converts a naive IST datetime into an aware IST datetime."""
        if dt.tzinfo is not None:
            return dt.astimezone(cls.IST)
        return cls.IST.localize(dt)
        
    @classmethod
    def datetime_to_utc_unix(cls, dt: datetime, is_naive_ist: bool = False) -> float:
        """Converts any datetime to an absolute UTC UNIX timestamp for external database synchronization."""
        if dt.tzinfo is None:
            if is_naive_ist:
                dt = cls.make_ist_aware(dt)
            else:
                # Assume UTC if it's naive but not IST
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).timestamp()
