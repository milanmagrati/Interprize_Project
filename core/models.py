"""
Content models for Celebra.

Every model here mirrors a structure that used to live in `sample_data.py`, and
deliberately exposes the same names the public templates already read
(`package.discount_percent`, `package.gallery`, `slide.image_srcset`, ...) as
properties. That is why none of the templates in `core/templates/` had to change
when the database arrived — the shapes are identical.

Images can come from either an upload (`image_file`) or an external URL
(`image_url`). The `image` property picks whichever is set and falls back to a
deterministic placeholder, so a half-filled record still renders a picture
instead of a broken <img>.

Everything editable lives here; `core/sample_data.py` is now only used by the
`seed_demo` management command to populate a fresh database.
"""

from collections import namedtuple

from django.conf import settings
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.text import slugify

IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "avif", "gif", "svg"]
VIDEO_EXTENSIONS = ["mp4", "webm", "ogv", "mov"]

# What a gallery entry has to look like for `package_detail.html`.
Shot = namedtuple("Shot", "url thumb alt")


def placeholder(seed, width, height):
    """A stable stand-in picture, so an empty field never renders a broken img."""
    return f"https://picsum.photos/seed/{seed}/{width}/{height}"


class Positioned(models.Model):
    """Hand-orderable rows. The panel's drag handles write `position`."""

    position = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Lower numbers appear first. Drag rows in the list to reorder.",
    )

    class Meta:
        abstract = True
        ordering = ["position", "id"]


class Timestamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PictureMixin(models.Model):
    """Upload *or* paste a URL. `image` resolves whichever is present."""

    image_file = models.FileField(
        upload_to="uploads/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(IMAGE_EXTENSIONS)],
        verbose_name="Upload an image",
        help_text="JPG, PNG, WebP, AVIF, GIF or SVG.",
    )
    image_url = models.URLField(
        blank=True,
        max_length=500,
        verbose_name="…or paste an image URL",
        help_text="Used only when nothing is uploaded.",
    )

    class Meta:
        abstract = True

    @property
    def image(self):
        if self.image_file:
            return self.image_file.url
        if self.image_url:
            return self.image_url
        return self.placeholder_image

    @property
    def placeholder_image(self):
        return placeholder(self.pk or "celebra", 800, 600)

    @property
    def has_own_image(self):
        return bool(self.image_file or self.image_url)


# ---------------------------------------------------------------------------
# Site-wide settings
# ---------------------------------------------------------------------------


class SiteSettingsManager(models.Manager):
    def current(self):
        """The one settings row, created on first read so the panel is never empty."""
        obj = self.first()
        if obj is None:
            obj = self.create()
        return obj


class SiteSettings(models.Model):
    """
    Singleton. Feeds `brand` in every template through the context processor.
    """

    name = models.CharField(max_length=80, default="Celebra")
    tagline = models.CharField(max_length=160, default="Celebrations, Beautifully Delivered")
    phone = models.CharField(max_length=40, default="+91 98765 43210")
    whatsapp = models.CharField(max_length=40, blank=True, default="+91 98765 43210")
    email = models.EmailField(default="hello@celebra.in")
    address = models.CharField(max_length=255, blank=True)
    hours = models.CharField(max_length=120, blank=True)
    founded_year = models.PositiveIntegerField(default=2019)

    instagram = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    twitter = models.URLField(blank=True)

    default_city = models.CharField(max_length=80, default="Bengaluru")
    free_delivery_threshold = models.PositiveIntegerField(
        default=3000, help_text="Cart subtotal above which delivery is free (₹)."
    )
    delivery_fee = models.PositiveIntegerField(default=249)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=18)

    maintenance_mode = models.BooleanField(
        default=False,
        help_text="Shows a holding notice on the public site. The panel stays reachable.",
    )
    announcement = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional strip shown above the header. Leave blank to hide it.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    objects = SiteSettingsManager()

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return self.name

    @property
    def phone_href(self):
        return "".join(ch for ch in self.phone if ch.isdigit() or ch == "+")

    def save(self, *args, **kwargs):
        # Enforce the singleton: any save writes to the first row.
        if not self.pk and SiteSettings.objects.exists():
            self.pk = SiteSettings.objects.values_list("pk", flat=True).first()
        return super().save(*args, **kwargs)


class NavLink(Positioned):
    label = models.CharField(max_length=60)
    url_name = models.CharField(
        max_length=80,
        default="core:home",
        help_text="A named route, e.g. core:categories.",
    )
    anchor = models.CharField(
        max_length=60, blank=True, help_text="Optional #fragment appended to the URL."
    )
    is_active = models.BooleanField(default=True)

    class Meta(Positioned.Meta):
        verbose_name = "Navigation link"

    def __str__(self):
        return self.label


class TrustBadge(Positioned):
    value = models.CharField(max_length=20, help_text="The big number, e.g. 100+")
    label = models.CharField(max_length=60, help_text="The line under it.")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.value} {self.label}"


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------


class City(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    state = models.CharField(max_length=80)
    is_metro = models.BooleanField(
        default=False, help_text="Metros show in the header's popular list."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Cities"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


class Category(Positioned, PictureMixin):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    icon = models.CharField(
        max_length=40,
        default="gift",
        help_text="Sprite id without the i- prefix: gift, heart, star, sparkles…",
    )
    blurb = models.CharField(max_length=200, help_text="One line, shown on the card.")
    price_from = models.PositiveIntegerField(default=1499)
    package_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Displayed setup count",
        help_text="The number shown on the card. Leave 0 to show the real count.",
    )
    is_active = models.BooleanField(default=True)

    class Meta(Positioned.Meta):
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("core:category_detail", args=[self.slug])

    @property
    def placeholder_image(self):
        return placeholder(f"cat-{self.slug}", 600, 450)

    @property
    def live_count(self):
        return self.packages.filter(is_active=True).count()

    @property
    def sample_count(self):
        """Real number of published packages — used on the categories index."""
        return self.live_count

    def display_count(self):
        return self.package_count or self.live_count


class PackageQuerySet(models.QuerySet):
    def live(self):
        return self.filter(is_active=True)

    def featured(self):
        return self.live().filter(is_featured=True)


class Package(Positioned, PictureMixin, Timestamped):
    title = models.CharField(max_length=140)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="packages"
    )
    price = models.PositiveIntegerField(help_text="What the customer pays (₹).")
    original_price = models.PositiveIntegerField(
        help_text="Struck-through price. The discount badge is worked out from this."
    )
    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        default=4.8,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    review_count = models.PositiveIntegerField(default=0)
    duration = models.CharField(max_length=80, blank=True, help_text="e.g. 3–4 hours on site")
    badge = models.CharField(
        max_length=40, blank=True, help_text="Corner ribbon. Blank hides it."
    )
    description = models.TextField()
    includes_text = models.TextField(
        blank=True,
        verbose_name="What's included",
        help_text="One item per line. Each line becomes a ticked bullet.",
    )
    is_featured = models.BooleanField(
        default=False, help_text="Featured packages fill the homepage grid."
    )
    is_active = models.BooleanField(
        default=True, help_text="Unpublish to hide it from the public site."
    )

    objects = PackageQuerySet.as_manager()

    class Meta(Positioned.Meta):
        ordering = ["position", "-is_featured", "-id"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:160]
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("core:package_detail", args=[self.slug])

    # -- derived fields the templates read ---------------------------------

    @property
    def placeholder_image(self):
        return placeholder(self.slug or "package", 800, 600)

    @property
    def saving(self):
        return max(self.original_price - self.price, 0)

    @property
    def discount_percent(self):
        if not self.original_price:
            return 0
        return round(self.saving * 100 / self.original_price)

    @property
    def category_name(self):
        return self.category.name

    @property
    def alt(self):
        return f"{self.title} decoration setup by Celebra"

    @property
    def includes(self):
        return [line.strip() for line in self.includes_text.splitlines() if line.strip()]

    # Short strings the panel's list table shows under the main value.
    @property
    def discount_label(self):
        return f"{self.discount_percent}% off" if self.discount_percent else "full price"

    @property
    def review_count_label(self):
        return f"{self.review_count} reviews"

    @property
    def gallery(self):
        """
        Detail-page photos. Falls back to five placeholders so a new package
        still has a working gallery before anyone uploads to it.
        """
        shots = [
            Shot(url=img.url, thumb=img.thumb, alt=img.alt or self.alt)
            for img in self.images.all()
        ]
        if shots:
            return shots
        seed = self.slug or "package"
        return [
            Shot(
                url=placeholder(f"{seed}-{i}", 1200, 900),
                thumb=placeholder(f"{seed}-{i}", 240, 180),
                alt=f"{self.title} — setup photo {i}",
            )
            for i in range(1, 6)
        ]


class PackageImage(Positioned, PictureMixin):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="images")
    alt = models.CharField(max_length=200, blank=True)

    class Meta(Positioned.Meta):
        verbose_name = "Gallery photo"

    def __str__(self):
        return self.alt or f"Photo {self.pk}"

    @property
    def placeholder_image(self):
        return placeholder(f"{self.package_id}-{self.pk}", 1200, 900)

    @property
    def url(self):
        return self.image

    @property
    def thumb(self):
        """Uploads have no derivatives, so the full file doubles as the thumb."""
        if self.image_file or self.image_url:
            return self.image
        return placeholder(f"{self.package_id}-{self.pk}", 240, 180)


# ---------------------------------------------------------------------------
# Hero slider
# ---------------------------------------------------------------------------


class HeroSlide(Positioned):
    """
    One frame of the homepage deck. See `core/templates/core/partials/
    _hero_slider.html` for how each field is used.
    """

    MEDIA_CHOICES = [("image", "Image"), ("video", "Video")]
    TINT_CHOICES = [
        ("night", "Night — deep charcoal green"),
        ("teal", "Teal — brand green"),
        ("plum", "Plum — warm aubergine"),
    ]

    key = models.SlugField(
        max_length=60,
        unique=True,
        blank=True,
        verbose_name="Slide id",
        help_text="Used in the slide's HTML id. Generated from the eyebrow if blank.",
    )
    media_type = models.CharField(max_length=10, choices=MEDIA_CHOICES, default="image")

    eyebrow = models.CharField(max_length=60, help_text="Small label above the heading.")
    heading = models.CharField(max_length=90, help_text="First line of the headline.")
    heading_accent = models.CharField(
        max_length=90, blank=True, help_text="Second line, rendered in italic display type."
    )
    description = models.TextField(help_text="Two lines at most reads best.")
    meta = models.CharField(
        max_length=120, blank=True, help_text="The small line under the buttons."
    )
    alt = models.CharField(max_length=200, help_text="Describe the picture for screen readers.")

    image_file = models.FileField(
        upload_to="hero/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(IMAGE_EXTENSIONS)],
        verbose_name="Background image",
        help_text="1920×1080 or larger. On video slides this becomes the poster frame.",
    )
    image_url = models.URLField(blank=True, max_length=500, verbose_name="…or an image URL")
    image_seed = models.CharField(
        max_length=80,
        blank=True,
        help_text="Placeholder seed, used only while no image is set.",
    )

    video_file = models.FileField(
        upload_to="hero/video/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(VIDEO_EXTENSIONS)],
        help_text="MP4, muted, no audio track, a few MB. Only used on video slides.",
    )
    video_mp4 = models.URLField(blank=True, max_length=500, verbose_name="…or an MP4 URL")
    video_webm = models.URLField(blank=True, max_length=500, verbose_name="Optional WebM URL")

    duration = models.PositiveIntegerField(
        default=6500, help_text="Milliseconds on screen before advancing."
    )
    tint = models.CharField(max_length=10, choices=TINT_CHOICES, default="night")
    focal = models.CharField(
        max_length=20,
        default="50% 50%",
        help_text="object-position for the crop, e.g. 50% 42%.",
    )

    cta_label = models.CharField(max_length=60, blank=True)
    cta_url_name = models.CharField(max_length=80, blank=True, default="core:categories")
    cta_url_arg = models.CharField(
        max_length=80, blank=True, help_text="Slug argument, when the route needs one."
    )
    cta_anchor = models.CharField(max_length=60, blank=True)

    cta2_label = models.CharField(max_length=60, blank=True)
    cta2_url_name = models.CharField(max_length=80, blank=True)
    cta2_url_arg = models.CharField(max_length=80, blank=True)
    cta2_anchor = models.CharField(max_length=60, blank=True)

    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(
        null=True, blank=True, help_text="Optional. Hidden before this moment."
    )
    ends_at = models.DateTimeField(
        null=True, blank=True, help_text="Optional. Hidden after this moment."
    )

    class Meta(Positioned.Meta):
        verbose_name = "Hero slide"

    def __str__(self):
        return f"{self.eyebrow} — {self.heading}"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = slugify(self.eyebrow or self.heading)[:60] or "slide"
        if not self.image_seed:
            self.image_seed = f"celebra-hero-{self.key}"
        return super().save(*args, **kwargs)

    # -- scheduling --------------------------------------------------------

    @property
    def is_live(self):
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    @property
    def schedule_state(self):
        """Label for the panel list: live, scheduled, expired or hidden."""
        if not self.is_active:
            return "hidden"
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return "scheduled"
        if self.ends_at and now > self.ends_at:
            return "expired"
        return "live"

    @property
    def heading_line(self):
        return " ".join(part for part in (self.heading, self.heading_accent) if part)

    @property
    def duration_label(self):
        return f"{self.duration / 1000:.1f}s".replace(".0s", "s")

    # -- media the template reads ------------------------------------------

    @property
    def is_video(self):
        return self.media_type == "video" and bool(self.video_file or self.video_mp4)

    @property
    def video_src(self):
        if self.video_file:
            return self.video_file.url
        return self.video_mp4

    @property
    def image(self):
        if self.image_file:
            return self.image_file.url
        if self.image_url:
            return self.image_url
        return placeholder(self.image_seed or "celebra-hero", 1920, 1080)

    @property
    def image_tall(self):
        if self.image_file:
            return self.image_file.url
        if self.image_url:
            return self.image_url
        return placeholder(self.image_seed or "celebra-hero", 1080, 1350)

    def _srcset(self, sizes):
        """
        An uploaded file has no derivatives, so it is offered at one width and
        the browser picks it regardless. Placeholders get a real width ladder.
        """
        if self.image_file or self.image_url:
            return ""
        seed = self.image_seed or "celebra-hero"
        return ", ".join(f"{placeholder(seed, w, h)} {w}w" for w, h in sizes)

    @property
    def image_srcset(self):
        return self._srcset([(1280, 720), (1920, 1080), (2560, 1440)])

    @property
    def image_tall_srcset(self):
        return self._srcset([(720, 900), (1080, 1350)])

    # -- links -------------------------------------------------------------

    @staticmethod
    def _resolve(url_name, arg="", anchor=""):
        if not url_name:
            return None
        try:
            path = reverse(url_name, args=[arg]) if arg else reverse(url_name)
        except NoReverseMatch:
            # A route was renamed or the slug no longer exists: fail soft, the
            # button just points at the homepage rather than 500-ing the page.
            path = "/"
        return f"{path}{anchor}"

    @property
    def cta_url(self):
        return self._resolve(self.cta_url_name, self.cta_url_arg, self.cta_anchor)

    @property
    def cta2_url(self):
        return self._resolve(self.cta2_url_name, self.cta2_url_arg, self.cta2_anchor)


# ---------------------------------------------------------------------------
# Social proof and copy blocks
# ---------------------------------------------------------------------------


class Testimonial(Positioned):
    name = models.CharField(max_length=80)
    city = models.CharField(max_length=80, blank=True)
    rating = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    occasion = models.CharField(
        max_length=140, blank=True, help_text="Usually the package they booked."
    )
    package = models.ForeignKey(
        Package,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="testimonials",
        help_text="Link it to a package and it shows on that package's page.",
    )
    date = models.CharField(
        max_length=40, blank=True, help_text="Shown as written, e.g. March 2026."
    )
    text = models.TextField()
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} — {self.rating}★"


class FAQ(Positioned):
    question = models.CharField(max_length=200)
    answer = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta(Positioned.Meta):
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class HowItWorksStep(Positioned):
    step = models.PositiveSmallIntegerField(default=1)
    title = models.CharField(max_length=80)
    icon = models.CharField(max_length=40, default="gift")
    text = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta(Positioned.Meta):
        verbose_name = "How-it-works step"

    def __str__(self):
        return f"{self.step}. {self.title}"


class Feature(Positioned):
    title = models.CharField(max_length=80)
    icon = models.CharField(max_length=40, default="shield")
    text = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class PricingRow(Positioned):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="pricing_rows"
    )
    range = models.CharField(max_length=60, verbose_name="Price range")
    popular = models.CharField(max_length=40, verbose_name="Most booked at")
    setup_time = models.CharField(max_length=40)
    is_active = models.BooleanField(default=True)

    class Meta(Positioned.Meta):
        verbose_name = "Pricing table row"

    def __str__(self):
        return f"{self.category} {self.range}"

    @property
    def slug(self):
        return self.category.slug


class TimeSlot(Positioned):
    label = models.CharField(max_length=40, help_text="e.g. 4 PM – 6 PM")
    value = models.CharField(max_length=20, help_text="Form value, e.g. 16-18")
    available = models.BooleanField(default=True)

    def __str__(self):
        return self.label


class AddOn(Positioned):
    name = models.CharField(max_length=80)
    price = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta(Positioned.Meta):
        verbose_name = "Add-on"

    def __str__(self):
        return f"{self.name} (+₹{self.price})"


# ---------------------------------------------------------------------------
# Operations — decorators, bookings, enquiries, coupons
# ---------------------------------------------------------------------------


class Decorator(models.Model):
    name = models.CharField(max_length=80)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    city = models.ForeignKey(
        City, null=True, blank=True, on_delete=models.SET_NULL, related_name="decorators"
    )
    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def open_jobs(self):
        return self.bookings.exclude(status__in=["completed", "cancelled"]).count()


class BookingQuerySet(models.QuerySet):
    def open(self):
        return self.exclude(status__in=["completed", "cancelled"])

    def upcoming(self):
        return self.open().filter(event_date__gte=timezone.localdate())

    def earning(self):
        """Rows that count towards revenue."""
        return self.exclude(status="cancelled")


class Booking(Timestamped):
    """
    A booked event. This is the operational heart of the panel: every setup the
    company is committed to delivering has one row here.
    """

    STATUS_CHOICES = [
        ("new", "New"),
        ("confirmed", "Confirmed"),
        ("assigned", "Decorator assigned"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    PAYMENT_CHOICES = [
        ("unpaid", "Unpaid"),
        ("advance", "Advance paid"),
        ("paid", "Paid in full"),
        ("refunded", "Refunded"),
    ]
    OPEN_STATUSES = ["new", "confirmed", "assigned"]

    reference = models.CharField(max_length=20, unique=True, blank=True, editable=False)

    customer_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40)

    package = models.ForeignKey(
        Package, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings"
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    add_ons = models.ManyToManyField(AddOn, blank=True, related_name="bookings")

    city = models.ForeignKey(
        City, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings"
    )
    address = models.TextField(blank=True)
    event_date = models.DateField(db_index=True)
    time_slot = models.CharField(max_length=40, blank=True)

    amount = models.PositiveIntegerField(
        default=0, help_text="Total charged (₹). Left at 0 it follows the package price."
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="new", db_index=True
    )
    payment_status = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default="unpaid")
    decorator = models.ForeignKey(
        Decorator, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings"
    )
    notes = models.TextField(blank=True, help_text="Access rules, surprises to keep, anything.")

    objects = BookingQuerySet.as_manager()

    class Meta:
        ordering = ["-event_date", "-id"]

    def __str__(self):
        return f"{self.reference} · {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._next_reference()
        if not self.amount and self.package_id:
            self.amount = self.package.price * self.quantity
        return super().save(*args, **kwargs)

    @staticmethod
    def _next_reference():
        last = Booking.objects.order_by("-id").values_list("id", flat=True).first() or 0
        return f"CEL-{1000 + last + 1}"

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_overdue(self):
        """Still open, but the date has passed — the thing the dashboard shouts about."""
        return self.is_open and self.event_date < timezone.localdate()

    @property
    def days_away(self):
        return (self.event_date - timezone.localdate()).days

    @property
    def created_label(self):
        return f"booked {timezone.localtime(self.created_at).strftime('%d %b')}"


class Enquiry(models.Model):
    """A contact-form message. Read-only in the panel apart from its status."""

    STATUS_CHOICES = [
        ("new", "New"),
        ("read", "Read"),
        ("replied", "Replied"),
        ("archived", "Archived"),
    ]

    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    city = models.CharField(max_length=80, blank=True)
    occasion = models.CharField(max_length=120, blank=True)
    event_date = models.DateField(null=True, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Enquiry"
        verbose_name_plural = "Enquiries"

    def __str__(self):
        return f"{self.name} — {self.occasion or 'general'}"


class Coupon(models.Model):
    KIND_CHOICES = [("percent", "Percent off"), ("flat", "Flat ₹ off")]

    code = models.CharField(max_length=30, unique=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="percent")
    value = models.PositiveIntegerField(help_text="15 means 15% or ₹15 depending on the kind.")
    min_order = models.PositiveIntegerField(default=0)
    max_uses = models.PositiveIntegerField(default=0, help_text="0 means unlimited.")
    used_count = models.PositiveIntegerField(default=0, editable=False)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        return super().save(*args, **kwargs)

    @property
    def is_live(self):
        if not self.is_active:
            return False
        today = timezone.localdate()
        if self.valid_from and today < self.valid_from:
            return False
        if self.valid_to and today > self.valid_to:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True

    @property
    def display_value(self):
        return f"{self.value}%" if self.kind == "percent" else f"₹{self.value}"

    @property
    def kind_label(self):
        return self.get_kind_display().lower()

    @property
    def usage_label(self):
        return f"{self.used_count} / {self.max_uses}" if self.max_uses else f"{self.used_count}"

    @property
    def state_label(self):
        if not self.is_active:
            return "hidden"
        today = timezone.localdate()
        if self.valid_to and today > self.valid_to:
            return "expired"
        if self.valid_from and today < self.valid_from:
            return "scheduled"
        if self.max_uses and self.used_count >= self.max_uses:
            return "used"
        return "live"


# ---------------------------------------------------------------------------
# Panel accounts
# ---------------------------------------------------------------------------


class StaffProfile(models.Model):
    """
    Extends the auth user with a panel role. Roles are checked in
    `panel/permissions.py`; Django's own is_staff/is_superuser are kept in sync
    so the built-in /admin/ stays consistent with what the panel shows.
    """

    ROLE_CHOICES = [
        ("owner", "Owner — everything, including staff accounts"),
        ("admin", "Admin — everything except staff accounts"),
        ("editor", "Editor — content and bookings, no settings"),
        ("viewer", "Viewer — read only"),
    ]
    RANK = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="editor")
    phone = models.CharField(max_length=40, blank=True)
    job_title = models.CharField(max_length=80, blank=True)
    theme = models.CharField(
        max_length=10,
        default="light",
        choices=[("light", "Light"), ("dark", "Dark")],
        help_text="Panel appearance. Only affects this account.",
    )
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "Staff member"

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display().split(' —')[0]})"

    @property
    def rank(self):
        return self.RANK.get(self.role, 0)

    def at_least(self, role):
        return self.rank >= self.RANK.get(role, 99)

    @property
    def can_write(self):
        return self.at_least("editor")

    @property
    def can_configure(self):
        return self.at_least("admin")

    @property
    def can_manage_staff(self):
        return self.at_least("owner")

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.get_username()

    @property
    def initials(self):
        parts = self.display_name.replace("_", " ").split()
        letters = "".join(p[0] for p in parts[:2])
        return letters.upper() or "?"


class InviteCode(models.Model):
    """
    Signup gate. The very first account bootstraps itself as owner; after that
    a new colleague needs a code an owner generated for them, so the signup URL
    can stay public without the panel being public.
    """

    code = models.CharField(max_length=32, unique=True)
    role = models.CharField(max_length=10, choices=StaffProfile.ROLE_CHOICES, default="editor")
    note = models.CharField(max_length=120, blank=True, help_text="Who is this for?")
    expires_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="used_invites",
    )
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_invites",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Invite code"

    def __str__(self):
        return self.code

    @property
    def is_usable(self):
        if self.used_by_id:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    @property
    def state(self):
        if self.used_by_id:
            return "used"
        if self.expires_at and timezone.now() > self.expires_at:
            return "expired"
        return "open"


class ActivityLog(models.Model):
    """Who changed what, written by the panel's generic CRUD views."""

    ACTION_CHOICES = [
        ("create", "Created"),
        ("update", "Updated"),
        ("delete", "Deleted"),
        ("bulk", "Bulk action"),
        ("auth", "Account"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity",
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_label = models.CharField(max_length=60)
    object_label = models.CharField(max_length=160, blank=True)
    detail = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Activity entry"
        verbose_name_plural = "Activity log"

    def __str__(self):
        return f"{self.user} {self.action} {self.model_label}"

    @classmethod
    def record(cls, user, action, obj=None, model_label="", detail=""):
        label = model_label or (obj._meta.verbose_name.title() if obj is not None else "")
        return cls.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            action=action,
            model_label=label,
            object_label=str(obj)[:160] if obj is not None else "",
            detail=detail[:240],
        )
