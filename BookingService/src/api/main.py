import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from fastapi import Depends, FastAPI, HTTPException, Path, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =============================================================================
# App and OpenAPI Metadata
# =============================================================================
openapi_tags = [
    {"name": "health", "description": "Service health and metadata"},
    {"name": "booking", "description": "Ticket booking and management"},
    {"name": "payment", "description": "Payment operations (stubbed)"},
    {"name": "analytics", "description": "Analytics and reports"},
    {"name": "admin", "description": "Administrative endpoints"},
]

app = FastAPI(
    title="Booking Service",
    description="Manages event ticket bookings: seat selection, reservations, payments, and e-tickets.",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

# =============================================================================
# CORS
# =============================================================================
allowed_origins = os.getenv("CORS_ALLOW_ORIGINS", "*")
allow_origins_list = [o.strip() for o in allowed_origins.split(",")] if allowed_origins else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Auth and RBAC Stubs
# =============================================================================

security = HTTPBearer(auto_error=False)

# Basic token parser stub:
# Expect "Bearer role:attendee|organizer|admin;user_id:<id>"
# If not provided, defaults to anonymous with no roles.
class Principal(BaseModel):
    user_id: Optional[str] = None
    roles: Set[str] = set()


def _parse_roles_from_token(token: str) -> Principal:
    """
    Very simple parser for a demo token.
    Format example:
        "role:attendee;user_id:123"
        "role:organizer;role:admin;user_id:42"
    """
    principal = Principal(user_id=None, roles=set())
    parts = [p.strip() for p in token.split(";") if p.strip()]
    for part in parts:
        if part.startswith("role:"):
            _, role = part.split(":", 1)
            principal.roles.add(role.strip())
        elif part.startswith("user_id:"):
            _, uid = part.split(":", 1)
            principal.user_id = uid.strip()
    return principal


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Principal:
    """
    Extract user and roles from Authorization header. This is a stub; in a real setup replace with JWT/OAuth2 validation.
    """
    if not credentials or not credentials.credentials:
        # anonymous user
        return Principal(user_id=None, roles=set())
    token = credentials.credentials
    return _parse_roles_from_token(token)


def require_roles(required: Set[str]):
    """
    Dependency factory to enforce RBAC.
    """
    def _checker(principal: Principal = Depends(get_current_user)) -> Principal:
        if not required.intersection(principal.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: requires one of roles {sorted(list(required))}",
            )
        return principal
    return _checker


# =============================================================================
# In-memory "Database"
# =============================================================================
# Data structures kept in memory for demonstration purposes only.
# In production replace with persistent storage and proper transactions/locking.

class SeatStatus(str):
    AVAILABLE = "available"
    RESERVED = "reserved"
    BOOKED = "booked"


class PaymentStatus(str):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class BookingStatus(str):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Seat(BaseModel):
    id: str
    label: str
    price: float
    status: str = Field(SeatStatus.AVAILABLE, description="Seat availability status")
    reservation_expires_at: Optional[datetime] = None  # for temporary holds


class EventSeats(BaseModel):
    event_id: str
    seats: Dict[str, Seat]  # seat_id -> Seat


class Payment(BaseModel):
    id: str
    booking_id: str
    amount: float
    currency: str = "USD"
    status: str = PaymentStatus.PENDING
    provider: str = "stub"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    provider_reference: Optional[str] = None
    failure_reason: Optional[str] = None


class ETicket(BaseModel):
    id: str
    booking_id: str
    code: str  # unique code for verification
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    pdf_url: Optional[str] = None  # stub link


class Booking(BaseModel):
    id: str
    event_id: str
    user_id: str
    seat_ids: List[str]
    total_amount: float
    status: str = BookingStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    payment_id: Optional[str] = None
    eticket_id: Optional[str] = None


# In-memory stores
EVENT_SEATS: Dict[str, EventSeats] = {}
BOOKINGS: Dict[str, Booking] = {}
PAYMENTS: Dict[str, Payment] = {}
ETICKETS: Dict[str, ETicket] = {}

# Analytics counters
ANALYTICS: Dict[str, Dict[str, float]] = {
    # per event_id
    # event_id: {"tickets_sold": int, "revenue": float}
}

# =============================================================================
# Pydantic Schemas for Requests / Responses
# =============================================================================

class SeatSelectionRequest(BaseModel):
    event_id: str = Field(..., description="Event identifier")
    seat_ids: List[str] = Field(..., description="List of seat ids to reserve or book")


class CreateReservationRequest(SeatSelectionRequest):
    hold_minutes: int = Field(10, description="Temporary reservation duration in minutes")


class PaymentInitiateRequest(BaseModel):
    booking_id: str = Field(..., description="Booking identifier to be paid")
    provider: str = Field("stub", description="Payment provider identifier")
    currency: str = Field("USD", description="Currency code (ISO-4217)")
    amount: Optional[float] = Field(None, description="Amount to charge; defaults to booking total")


class PaymentCallbackRequest(BaseModel):
    payment_id: str = Field(..., description="Payment ID")
    status: str = Field(..., description="Final status reported by provider (success/failed)")
    provider_reference: Optional[str] = Field(None, description="Provider transaction reference")
    failure_reason: Optional[str] = Field(None, description="Reason for failure if any")


class BookingCreateRequest(BaseModel):
    event_id: str = Field(..., description="Event id")
    seat_ids: List[str] = Field(..., description="Seat ids to book")
    auto_pay: bool = Field(False, description="If true, simulate immediate payment success for demo")


class BookingPublic(BaseModel):
    id: str
    event_id: str
    user_id: str
    seat_ids: List[str]
    total_amount: float
    status: str
    created_at: datetime
    updated_at: datetime
    payment_id: Optional[str] = None
    eticket_id: Optional[str] = None


class SeatPublic(BaseModel):
    id: str
    label: str
    price: float
    status: str


class EventSeatMapResponse(BaseModel):
    event_id: str
    seats: List[SeatPublic]


class AnalyticsSummary(BaseModel):
    event_id: str
    tickets_sold: int
    revenue: float


# =============================================================================
# Utility functions
# =============================================================================

def _ensure_event(event_id: str) -> EventSeats:
    # Initialize demo event seats if not present
    if event_id not in EVENT_SEATS:
        # Create a default small map for demo purposes
        seats: Dict[str, Seat] = {}
        # 3 rows x 5 seats
        base_price = 50.0
        for r in ["A", "B", "C"]:
            for i in range(1, 6):
                sid = f"{r}{i}"
                seats[sid] = Seat(id=sid, label=f"{r}-{i}", price=base_price + (5 * i))
        EVENT_SEATS[event_id] = EventSeats(event_id=event_id, seats=seats)
    return EVENT_SEATS[event_id]


def _cleanup_expired_reservations(event: EventSeats) -> None:
    # Expire temporary reservations
    now = datetime.utcnow()
    for s in event.seats.values():
        if s.status == SeatStatus.RESERVED and s.reservation_expires_at and s.reservation_expires_at <= now:
            s.status = SeatStatus.AVAILABLE
            s.reservation_expires_at = None


def _calculate_total(event: EventSeats, seat_ids: List[str]) -> float:
    total = 0.0
    for sid in seat_ids:
        if sid not in event.seats:
            raise HTTPException(status_code=404, detail=f"Seat {sid} not found")
        total += event.seats[sid].price
    return total


def _reserve_seats(event: EventSeats, seat_ids: List[str], hold_minutes: int) -> None:
    _cleanup_expired_reservations(event)
    now = datetime.utcnow()
    # Validate availability
    for sid in seat_ids:
        if sid not in event.seats:
            raise HTTPException(status_code=404, detail=f"Seat {sid} not found")
        seat = event.seats[sid]
        if seat.status != SeatStatus.AVAILABLE:
            raise HTTPException(status_code=409, detail=f"Seat {sid} is not available")
    # Reserve
    for sid in seat_ids:
        seat = event.seats[sid]
        seat.status = SeatStatus.RESERVED
        seat.reservation_expires_at = now + timedelta(minutes=hold_minutes)


def _book_seats(event: EventSeats, seat_ids: List[str]) -> None:
    _cleanup_expired_reservations(event)
    # Validate they are either available or reserved (and not expired)
    now = datetime.utcnow()
    for sid in seat_ids:
        if sid not in event.seats:
            raise HTTPException(status_code=404, detail=f"Seat {sid} not found")
        seat = event.seats[sid]
        if seat.status == SeatStatus.RESERVED and seat.reservation_expires_at and seat.reservation_expires_at <= now:
            # expired; treat as available
            seat.status = SeatStatus.AVAILABLE
            seat.reservation_expires_at = None
        if seat.status not in {SeatStatus.AVAILABLE, SeatStatus.RESERVED}:
            raise HTTPException(status_code=409, detail=f"Seat {sid} is not bookable")
    # Book them
    for sid in seat_ids:
        seat = event.seats[sid]
        seat.status = SeatStatus.BOOKED
        seat.reservation_expires_at = None


def _release_seats(event: EventSeats, seat_ids: List[str]) -> None:
    for sid in seat_ids:
        if sid in event.seats:
            seat = event.seats[sid]
            seat.status = SeatStatus.AVAILABLE
            seat.reservation_expires_at = None


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _issue_eticket(booking: Booking) -> ETicket:
    eticket_id = _gen_id("tkt")
    eticket_code = secrets.token_urlsafe(12)
    eticket = ETicket(id=eticket_id, booking_id=booking.id, code=eticket_code, pdf_url=f"https://example.com/tickets/{eticket_id}.pdf")
    ETICKETS[eticket_id] = eticket
    booking.eticket_id = eticket_id
    return eticket


def _analytics_add(event_id: str, tickets: int, amount: float) -> None:
    entry = ANALYTICS.setdefault(event_id, {"tickets_sold": 0, "revenue": 0.0})
    entry["tickets_sold"] += tickets
    entry["revenue"] += amount


# =============================================================================
# Routes
# =============================================================================

@app.get("/", tags=["health"], summary="Health check")
def health_check():
    """Simple health check endpoint."""
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.get(
    "/events/{event_id}/seats",
    tags=["booking"],
    summary="Get seat map",
    description="Retrieve seat map and statuses for the event.",
    response_model=EventSeatMapResponse,
)
def get_seat_map(
    event_id: str = Path(..., description="Event identifier"),
):
    """Return the current seat map for an event."""
    event = _ensure_event(event_id)
    _cleanup_expired_reservations(event)
    seats = [SeatPublic(id=s.id, label=s.label, price=s.price, status=s.status) for s in event.seats.values()]
    return EventSeatMapResponse(event_id=event_id, seats=seats)


# PUBLIC_INTERFACE
@app.post(
    "/reservations",
    tags=["booking"],
    summary="Create seat reservation (hold)",
    description="Temporarily holds selected seats for a duration to prevent double-booking.",
    response_model=BookingPublic,
    responses={
        403: {"description": "Forbidden"},
        409: {"description": "Seat not available"},
    },
)
def create_reservation(
    req: CreateReservationRequest,
    principal: Principal = Depends(require_roles({"attendee", "organizer", "admin"})),
):
    """
    Create a temporary reservation which places a hold on the selected seats for the specified minutes.
    Returns a booking in 'pending' status with no payment yet.
    """
    event = _ensure_event(req.event_id)
    _reserve_seats(event, req.seat_ids, req.hold_minutes)
    total = _calculate_total(event, req.seat_ids)
    booking_id = _gen_id("bkg")
    booking = Booking(
        id=booking_id,
        event_id=req.event_id,
        user_id=principal.user_id or "anonymous",
        seat_ids=list(req.seat_ids),
        total_amount=total,
        status=BookingStatus.PENDING,
    )
    BOOKINGS[booking_id] = booking
    return BookingPublic(**booking.model_dump())


# PUBLIC_INTERFACE
@app.post(
    "/bookings",
    tags=["booking"],
    summary="Create booking",
    description="Creates a booking and marks seats as booked. Optionally auto-pays using a stub provider.",
    response_model=BookingPublic,
)
def create_booking(
    req: BookingCreateRequest,
    principal: Principal = Depends(require_roles({"attendee", "organizer", "admin"})),
):
    """
    Create a booking and mark the seats as booked. If auto_pay is true, simulate payment success, confirm booking,
    and issue an e-ticket.
    """
    event = _ensure_event(req.event_id)
    _book_seats(event, req.seat_ids)
    total = _calculate_total(event, req.seat_ids)
    booking_id = _gen_id("bkg")
    booking = Booking(
        id=booking_id,
        event_id=req.event_id,
        user_id=principal.user_id or "anonymous",
        seat_ids=list(req.seat_ids),
        total_amount=total,
        status=BookingStatus.PENDING,
    )
    BOOKINGS[booking_id] = booking

    if req.auto_pay:
        # Simulate payment and confirmation
        payment_id = _gen_id("pay")
        payment = Payment(id=payment_id, booking_id=booking_id, amount=total, status=PaymentStatus.SUCCESS)
        PAYMENTS[payment_id] = payment
        booking.payment_id = payment_id
        booking.status = BookingStatus.CONFIRMED
        booking.updated_at = datetime.utcnow()
        _analytics_add(booking.event_id, tickets=len(booking.seat_ids), amount=booking.total_amount)
        _issue_eticket(booking)

    return BookingPublic(**booking.model_dump())


# PUBLIC_INTERFACE
@app.get(
    "/bookings/{booking_id}",
    tags=["booking"],
    summary="Get booking",
    description="Retrieve a booking by id (owner, organizer for their event, or admin).",
    response_model=BookingPublic,
)
def get_booking(
    booking_id: str = Path(..., description="Booking identifier"),
    principal: Principal = Depends(get_current_user),
):
    """Return booking if user is owner or has organizer/admin role."""
    if booking_id not in BOOKINGS:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking = BOOKINGS[booking_id]
    # Ownership or elevated roles
    if booking.user_id != (principal.user_id or "") and not principal.roles.intersection({"organizer", "admin"}):
        raise HTTPException(status_code=403, detail="Forbidden")
    return BookingPublic(**booking.model_dump())


# PUBLIC_INTERFACE
@app.post(
    "/payments/initiate",
    tags=["payment"],
    summary="Initiate payment (stub)",
    description="Initiate a payment for a given booking using a stub provider.",
    response_model=Payment,
)
def initiate_payment(
    req: PaymentInitiateRequest,
    principal: Principal = Depends(require_roles({"attendee", "organizer", "admin"})),
):
    """Create a pending payment record for the booking."""
    if req.booking_id not in BOOKINGS:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking = BOOKINGS[req.booking_id]
    # Only owner or admin/organizer can initiate payment
    if booking.user_id != (principal.user_id or "") and not principal.roles.intersection({"organizer", "admin"}):
        raise HTTPException(status_code=403, detail="Forbidden")

    if booking.payment_id:
        pay = PAYMENTS.get(booking.payment_id)
        if pay and pay.status == PaymentStatus.SUCCESS:
            raise HTTPException(status_code=409, detail="Payment already completed")

    payment_id = _gen_id("pay")
    amount = req.amount if req.amount is not None else booking.total_amount
    payment = Payment(
        id=payment_id,
        booking_id=booking.id,
        amount=amount,
        currency=req.currency,
        status=PaymentStatus.PENDING,
        provider=req.provider,
    )
    PAYMENTS[payment_id] = payment
    booking.payment_id = payment_id
    booking.updated_at = datetime.utcnow()
    return payment


# PUBLIC_INTERFACE
@app.post(
    "/payments/callback",
    tags=["payment"],
    summary="Payment callback (stub)",
    description="Simulate payment provider callback to update payment and booking status.",
    response_model=Payment,
)
def payment_callback(req: PaymentCallbackRequest):
    """
    This simulates the external payment provider calling back with final status.
    On success: booking confirmed, seats remain booked, and e-ticket is issued.
    On failure: release seats and mark booking cancelled.
    """
    payment = PAYMENTS.get(req.payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    booking = BOOKINGS.get(payment.booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    payment.status = PaymentStatus.SUCCESS if req.status.lower() == "success" else PaymentStatus.FAILED
    payment.provider_reference = req.provider_reference
    payment.failure_reason = req.failure_reason
    payment.updated_at = datetime.utcnow()

    event = _ensure_event(booking.event_id)

    if payment.status == PaymentStatus.SUCCESS:
        booking.status = BookingStatus.CONFIRMED
        booking.updated_at = datetime.utcnow()
        _analytics_add(booking.event_id, tickets=len(booking.seat_ids), amount=booking.total_amount)
        _issue_eticket(booking)
    else:
        # Failure: release seats and cancel booking
        _release_seats(event, booking.seat_ids)
        booking.status = BookingStatus.CANCELLED
        booking.updated_at = datetime.utcnow()

    return payment


# PUBLIC_INTERFACE
@app.post(
    "/bookings/{booking_id}/cancel",
    tags=["booking"],
    summary="Cancel booking",
    description="Cancels a booking if not confirmed; if confirmed, seats remain booked and refund flow can be applied.",
    response_model=BookingPublic,
)
def cancel_booking(
    booking_id: str = Path(..., description="Booking identifier"),
    principal: Principal = Depends(require_roles({"attendee", "organizer", "admin"})),
):
    """Cancel a booking. If pending, release seats. If confirmed, mark refunded via admin/payment policy."""
    booking = BOOKINGS.get(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.user_id != (principal.user_id or "") and not principal.roles.intersection({"organizer", "admin"}):
        raise HTTPException(status_code=403, detail="Forbidden")

    event = _ensure_event(booking.event_id)

    if booking.status == BookingStatus.PENDING:
        _release_seats(event, booking.seat_ids)
        booking.status = BookingStatus.CANCELLED
        booking.updated_at = datetime.utcnow()
    elif booking.status == BookingStatus.CONFIRMED:
        # In demo, mark refunded and release seats
        _release_seats(event, booking.seat_ids)
        booking.status = BookingStatus.REFUNDED
        booking.updated_at = datetime.utcnow()
        if booking.payment_id and booking.payment_id in PAYMENTS:
            pay = PAYMENTS[booking.payment_id]
            pay.status = PaymentStatus.REFUNDED
            pay.updated_at = datetime.utcnow()
        # Adjust analytics negative (simple demo - in reality keep ledger and compute reports)
        entry = ANALYTICS.setdefault(booking.event_id, {"tickets_sold": 0, "revenue": 0.0})
        entry["tickets_sold"] = max(0, int(entry.get("tickets_sold", 0)) - len(booking.seat_ids))
        entry["revenue"] = max(0.0, float(entry.get("revenue", 0.0)) - booking.total_amount)
    else:
        # already cancelled or refunded
        pass

    return BookingPublic(**booking.model_dump())


# PUBLIC_INTERFACE
@app.get(
    "/analytics/events/{event_id}/summary",
    tags=["analytics"],
    summary="Event analytics summary",
    description="Get tickets sold and revenue for an event.",
    response_model=AnalyticsSummary,
)
def analytics_summary(
    event_id: str = Path(..., description="Event id"),
    principal: Principal = Depends(require_roles({"organizer", "admin"})),
):
    """Return basic analytics for the event."""
    entry = ANALYTICS.get(event_id, {"tickets_sold": 0, "revenue": 0.0})
    return AnalyticsSummary(event_id=event_id, tickets_sold=int(entry.get("tickets_sold", 0)), revenue=float(entry.get("revenue", 0.0)))


# PUBLIC_INTERFACE
@app.get(
    "/docs/websocket-usage",
    tags=["health"],
    summary="WebSocket usage notes",
    description="This service currently does not expose WebSockets. This endpoint is reserved for documenting real-time features in the future.",
)
def websocket_usage_note():
    """Usage note for future WebSocket endpoints."""
    return {"note": "No WebSocket endpoints currently. Future real-time seat updates could be published here."}
