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

The inventory models near the bottom are the one part that is not content: an
item's `quantity` is never written directly, only through `StockMovement`, so
the ledger and the shelf can never disagree.
"""

from collections import defaultdict, namedtuple
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models, transaction
from django.db.models.functions import Coalesce
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

    name = models.CharField(max_length=80, default="Barahi Florist & Events")
    tagline = models.CharField(max_length=160, default="Florist and Event Decorators")

    LOGO_FIT_CHOICES = [
        ("contain", "Fit inside the box, no cropping"),
        ("cover", "Fill the box, cropping the edges"),
    ]

    logo_file = models.FileField(
        upload_to="branding/",
        blank=True,
        validators=[FileExtensionValidator(IMAGE_EXTENSIONS)],
        verbose_name="Logo",
        help_text="PNG, WebP or SVG with a transparent background works best.",
    )
    logo_url = models.URLField(blank=True, max_length=500, verbose_name="…or a logo URL")
    logo_fit = models.CharField(
        max_length=10,
        choices=LOGO_FIT_CHOICES,
        default="contain",
        verbose_name="How the logo fits its box",
    )
    logo_focal = models.CharField(
        max_length=20,
        default="50% 50%",
        verbose_name="Logo crop position",
        help_text=(
            "Which part of the image stays visible when it's cropped, e.g. "
            "'50% 50%' for centred or '20% 50%' to favour the left. Only used "
            "when filling & cropping."
        ),
    )
    logo_width = models.PositiveIntegerField(
        default=48,
        validators=[MinValueValidator(24), MaxValueValidator(320)],
        verbose_name="Logo box width (px)",
        help_text=(
            "How wide the logo sits in the header. The height is fixed, so this "
            "is what shapes the box: leave it near 48 for a square mark, or "
            "raise it to 150–220 for a wide logo that includes the name. When "
            "filling & cropping, a wider box crops away the empty space above "
            "and below the artwork."
        ),
    )
    logo_height = models.PositiveIntegerField(
        default=48,
        validators=[MinValueValidator(24), MaxValueValidator(320)],
        verbose_name="Logo box height (px)",
        help_text=(
            "How tall the logo sits in the header. Paired with the width to "
            "control exact logo dimensions."
        ),
    )
    logo_show_name = models.BooleanField(
        default=True,
        verbose_name="Show site name next to logo",
        help_text=(
            "Turn off if the logo image already contains the brand name, so "
            "the text does not repeat."
        ),
    )
    phone = models.CharField(max_length=40, default="+91 98765 43210")
    whatsapp = models.CharField(max_length=40, blank=True, default="+91 98765 43210")
    email = models.EmailField(default="hello@barahiflorist.com")
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

    # -- the products section, on the homepage and on its own page ---------
    PRODUCT_SOURCE_CHOICES = [
        ("featured", "Featured first"),
        ("newest", "Newest first"),
        ("rating", "Highest rated"),
        ("discount", "Biggest discount"),
        ("popular", "Most reviewed"),
        ("manual", "The order you dragged them into"),
    ]

    home_products_eyebrow = models.CharField(
        max_length=60,
        default="Featured setups",
        verbose_name="Homepage eyebrow",
        help_text="The small line above the heading of the homepage products block.",
    )
    home_products_title = models.CharField(
        max_length=120,
        default="Booked most this month",
        verbose_name="Homepage heading",
    )
    home_products_lead = models.CharField(
        max_length=240,
        blank=True,
        default=(
            "Every price below is final: materials, labour, travel inside city "
            "limits and clean-up."
        ),
        verbose_name="Homepage sub-heading",
    )
    home_products_limit = models.PositiveIntegerField(
        default=8,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
        verbose_name="How many to show at home",
        help_text="The homepage shows this many products; the rest live on the products page.",
    )
    home_products_source = models.CharField(
        max_length=20,
        choices=PRODUCT_SOURCE_CHOICES,
        default="featured",
        verbose_name="Which ones to show",
    )
    home_products_cta_label = models.CharField(
        max_length=60,
        default="See all products",
        verbose_name="Button under the grid",
        help_text="Links to the products page. Leave blank to hide the button.",
        blank=True,
    )

    products_page_eyebrow = models.CharField(
        max_length=60, default="The full catalogue", verbose_name="Products page eyebrow"
    )
    products_page_title = models.CharField(
        max_length=120,
        default="Every setup we build",
        verbose_name="Products page heading",
    )
    products_page_lead = models.CharField(
        max_length=240,
        blank=True,
        default=(
            "Filter by occasion, budget and rating. Every price is final and "
            "includes delivery, setup and clean-up."
        ),
        verbose_name="Products page sub-heading",
    )
    products_per_page = models.PositiveIntegerField(
        default=9,
        validators=[MinValueValidator(3), MaxValueValidator(48)],
        verbose_name="Products per page",
    )

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

    @property
    def logo(self):
        if self.logo_file:
            return self.logo_file.url
        if self.logo_url:
            return self.logo_url
        return ""

    @property
    def has_logo(self):
        return bool(self.logo_file or self.logo_url)

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
        return f"{self.title} decoration setup by Barahi Florist & Events"

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
# Operations — staff, bookings, enquiries, coupons
# ---------------------------------------------------------------------------


class StaffCategory(Positioned):
    """
    The kind of work a staff member does: decorator, florist, photographer,
    driver, whatever this company ends up hiring for.

    Types are rows rather than a hard-coded choice list, so adding one is a
    record in the panel instead of a migration.
    """

    KIND_CHOICES = [
        ("field", "Field crew — on site at the event"),
        ("office", "Office — coordination and support"),
        ("partner", "Partner — vendor or agency"),
    ]
    TONE_CHOICES = [
        ("green", "Green"),
        ("blue", "Blue"),
        ("violet", "Violet"),
        ("amber", "Amber"),
        ("red", "Red"),
        ("grey", "Grey"),
    ]

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True, blank=True)
    kind = models.CharField(
        max_length=10,
        choices=KIND_CHOICES,
        default="field",
        verbose_name="Group",
        help_text="The broad bucket this type belongs to. Used to filter the staff list.",
    )
    tone = models.CharField(
        max_length=10,
        choices=TONE_CHOICES,
        default="grey",
        verbose_name="Badge colour",
        help_text="The colour this type wears wherever it is shown.",
    )
    description = models.CharField(
        max_length=200, blank=True, help_text="What this type is responsible for."
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Selectable",
        help_text="Turn off to retire a type. Existing staff keep it; new ones cannot pick it.",
    )

    class Meta(Positioned.Meta):
        verbose_name = "Staff type"
        verbose_name_plural = "Staff types"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)

    @property
    def member_total(self):
        return self.members.count()

    @property
    def active_total(self):
        return self.members.filter(is_active=True).count()

    @property
    def open_jobs(self):
        return (
            Booking.objects.filter(staff__category=self)
            .exclude(status__in=["completed", "cancelled"])
            .count()
        )


class StaffMemberQuerySet(models.QuerySet):
    def assignable(self):
        """Who may be put on a booking."""
        return self.filter(is_active=True)

    def of_type(self, slug):
        return self.filter(category__slug=slug)

    def without_login(self):
        return self.filter(account__isnull=True)


class StaffMember(models.Model):
    """
    Somebody who works a booking — the decorator crew, the florist, the driver.

    This is the *operational* record: who they are, what they do and how busy
    they are. A control-panel login is a separate thing (`StaffProfile`); the
    two are joined by `account` when a staff member also needs to sign in, and
    plenty of staff never do.
    """

    EMPLOYMENT_CHOICES = [
        ("inhouse", "In-house"),
        ("freelance", "Freelance"),
        ("vendor", "Vendor / agency"),
        ("intern", "Intern"),
    ]

    name = models.CharField(max_length=80)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    category = models.ForeignKey(
        "StaffCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
        verbose_name="Staff type",
        help_text="What they do. The list is managed under Staff types.",
    )
    employment = models.CharField(
        max_length=12,
        choices=EMPLOYMENT_CHOICES,
        default="inhouse",
        verbose_name="Engagement",
        help_text="How this person is engaged.",
    )
    skills = models.CharField(
        max_length=160,
        blank=True,
        help_text="Comma separated — balloons, mandap, drone. Shown when you assign a booking.",
    )
    city = models.ForeignKey(
        City, null=True, blank=True, on_delete=models.SET_NULL, related_name="staff_members"
    )
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_member",
        verbose_name="Panel login",
        help_text="The control-panel account this person signs in with, if they have one.",
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

    objects = StaffMemberQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name = "Staff member"
        verbose_name_plural = "Staffs"

    def __str__(self):
        return self.name

    @property
    def open_jobs(self):
        return self.bookings.exclude(status__in=["completed", "cancelled"]).count()

    @property
    def done_jobs(self):
        return self.bookings.filter(status="completed").count()

    @property
    def type_name(self):
        return self.category.name if self.category_id else ""

    @property
    def type_tone(self):
        return self.category.tone if self.category_id else "grey"

    @property
    def skill_list(self):
        return [bit.strip() for bit in self.skills.split(",") if bit.strip()]

    @property
    def contact_line(self):
        return self.phone or self.email or "No contact on file"

    @property
    def account_role(self):
        """The panel role of the linked login, or "" when this person has none."""
        if not self.account_id:
            return ""
        profile = getattr(self.account, "staff_profile", None)
        return profile.role if profile else ""

    @property
    def initials(self):
        letters = "".join(part[0] for part in self.name.split()[:2])
        return letters.upper() or "?"

    @property
    def assign_label(self):
        """How this person reads in a booking's assignment dropdown."""
        bits = [self.name]
        if self.category_id:
            bits.append(self.category.name)
        if self.city_id:
            bits.append(self.city.name)
        return " · ".join(bits)


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
        ("assigned", "Staff assigned"),
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
    staff = models.ForeignKey(
        StaffMember,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bookings",
        verbose_name="Assigned to",
        help_text="Who is doing this job. Filter the list by staff type when you pick.",
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
# Inventory — suppliers, stock, the ledger, and the counter
# ---------------------------------------------------------------------------


def normalise_quantity(value):
    """`3.00` reads as `3`, `2.50` stays `2.5` — quantities are shown, not calculated."""
    number = Decimal(str(value or 0)).normalize()
    if number == number.to_integral_value():
        number = number.quantize(Decimal(1))
    return f"{number:f}"


class Supplier(models.Model):
    """Whoever the stock is bought from. Purchases point back at one of these."""

    name = models.CharField(max_length=120, unique=True)
    contact_name = models.CharField(
        max_length=80, blank=True, verbose_name="Contact person"
    )
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    gst_number = models.CharField(max_length=20, blank=True, verbose_name="GSTIN")
    lead_time_days = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Lead time (days)",
        help_text="How long an order usually takes to arrive. 0 if it is bought over the counter.",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(
        default=True,
        verbose_name="Selectable",
        help_text="Turn off to retire a supplier. Existing stock keeps them.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def item_total(self):
        return self.items.count()

    @property
    def contact_line(self):
        return self.phone or self.email or "No contact on file"

    @property
    def stock_value(self):
        """What this supplier's goods, sitting on the shelf right now, cost."""
        return sum(item.stock_value for item in self.items.all())


class StockCategory(Positioned):
    """
    How the store room is divided up — balloons, fabric, lighting, crockery.

    Deliberately separate from the public `Category`: an occasion is what a
    customer browses, a stock group is where a thing lives on a shelf.
    """

    TONE_CHOICES = StaffCategory.TONE_CHOICES

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True, blank=True)
    description = models.CharField(
        max_length=200, blank=True, help_text="What belongs in this group."
    )
    tone = models.CharField(
        max_length=10,
        choices=TONE_CHOICES,
        default="grey",
        verbose_name="Badge colour",
        help_text="The colour this group wears wherever it is shown.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Selectable",
        help_text="Turn off to retire a group. Existing items keep it.",
    )

    class Meta(Positioned.Meta):
        verbose_name = "Stock group"
        verbose_name_plural = "Stock groups"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)

    @property
    def item_total(self):
        return self.items.count()

    @property
    def stock_value(self):
        return sum(item.stock_value for item in self.items.all())

    @property
    def low_total(self):
        return sum(1 for item in self.items.all() if item.is_low or item.is_out)


class InventoryItemQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def sellable(self):
        """What the counter screen is allowed to ring up."""
        return self.filter(is_active=True, is_sellable=True)

    def in_stock(self):
        return self.filter(quantity__gt=0)

    def out_of_stock(self):
        return self.filter(quantity__lte=0)

    def low_stock(self):
        """At or under the reorder level, but not yet empty."""
        return self.filter(
            quantity__gt=0, reorder_level__gt=0, quantity__lte=models.F("reorder_level")
        )

    def needs_attention(self):
        return self.active().filter(
            models.Q(quantity__lte=0)
            | models.Q(reorder_level__gt=0, quantity__lte=models.F("reorder_level"))
        )

    def with_reserved(self):
        """
        Annotate `reserved_total`: units held for events right now. A subquery
        rather than a join, so it never multiplies rows or forces a GROUP BY on
        whatever else the list has annotated.
        """
        money = models.DecimalField(max_digits=12, decimal_places=2)
        held = (
            EventItem.objects.filter(inventory_item=models.OuterRef("pk"))
            .order_by()
            .values("inventory_item")
            .annotate(total=models.Sum(EventItem.outstanding_expression(), output_field=money))
            .values("total")
        )
        return self.annotate(
            reserved_total=Coalesce(
                models.Subquery(held, output_field=money),
                models.Value(Decimal("0")),
                output_field=money,
            )
        )


class InventoryItem(PictureMixin, Timestamped):
    """
    One thing on a shelf: a stock-keeping unit with a cost, a price and a count.

    `quantity` is a running total kept in step by `StockMovement` — nothing
    writes it directly. Every change goes through a ledger row, so the history
    and the number on the card can never drift apart.
    """

    UNIT_CHOICES = [
        ("piece", "Piece"),
        ("pack", "Pack"),
        ("box", "Box"),
        ("set", "Set"),
        ("pair", "Pair"),
        ("roll", "Roll"),
        ("metre", "Metre"),
        ("kg", "Kilogram"),
        ("litre", "Litre"),
        ("hour", "Hour"),
    ]
    UNIT_SHORT = {
        "piece": "pc", "pack": "pack", "box": "box", "set": "set", "pair": "pr",
        "roll": "roll", "metre": "m", "kg": "kg", "litre": "L", "hour": "hr",
    }
    USAGE_CHOICES = [
        ("consumable", "Consumable — used up (water, plates, flowers)"),
        ("reusable", "Reusable — comes back (chairs, speakers, lights)"),
    ]

    sku = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        verbose_name="SKU",
        help_text="Left blank, one is made from the name.",
    )
    name = models.CharField(max_length=120)
    category = models.ForeignKey(
        StockCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="items",
        verbose_name="Stock group",
        help_text="Where this lives. The list is managed under Stock groups.",
    )
    supplier = models.ForeignKey(
        Supplier,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="items",
        help_text="Who this is normally bought from.",
    )
    description = models.TextField(blank=True)
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default="piece",
        verbose_name="Counted in",
        help_text="What one of these is.",
    )
    usage_type = models.CharField(
        max_length=12,
        choices=USAGE_CHOICES,
        default="consumable",
        db_index=True,
        verbose_name="Kind of stock",
        help_text=(
            "Reusable stock is only reserved for an event and comes back "
            "afterwards. Consumable stock is used up and leaves the shelf."
        ),
    )
    barcode = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        help_text="Optional. The counter search looks at this too, so a scanner works.",
    )
    location = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Shelf",
        help_text="Where to find it — rack, shelf, room.",
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        verbose_name="In stock",
        help_text="Kept in step by the stock ledger. Use an adjustment to change it.",
    )
    reorder_level = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Reorder at",
        help_text="Drop to this and the item is flagged as running low. 0 turns the warning off.",
    )
    cost_price = models.PositiveIntegerField(
        default=0, help_text="What one costs you (₹)."
    )
    sale_price = models.PositiveIntegerField(
        default=0, help_text="What one sells for at the counter (₹)."
    )

    is_sellable = models.BooleanField(
        default=True,
        verbose_name="Sell at the counter",
        help_text="Off for consumables you track but never sell over the counter.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text="Turn off to retire an item without losing its history.",
    )
    notes = models.TextField(blank=True)

    objects = InventoryItemQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name = "Stock item"
        verbose_name_plural = "Stock items"
        indexes = [models.Index(fields=["is_active", "quantity"])]

    def __str__(self):
        return f"{self.name} ({self.sku})" if self.sku else self.name

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = self._next_sku()
        self.sku = self.sku.upper().strip()
        return super().save(*args, **kwargs)

    def _next_sku(self):
        """A readable code — three letters of the name, then a running number."""
        stem = "".join(ch for ch in self.name.upper() if ch.isalnum())[:3] or "ITM"
        number = InventoryItem.objects.count() + 1
        while InventoryItem.objects.filter(sku=f"{stem}-{number:04d}").exists():
            number += 1
        return f"{stem}-{number:04d}"

    # -- money ------------------------------------------------------------

    @property
    def stock_value(self):
        """What is on the shelf, at what it cost."""
        return int(self.quantity * self.cost_price)

    @property
    def retail_value(self):
        return int(self.quantity * self.sale_price)

    @property
    def margin(self):
        return self.sale_price - self.cost_price

    @property
    def margin_percent(self):
        if not self.sale_price:
            return 0
        return round(self.margin * 100 / self.sale_price)

    @property
    def margin_label(self):
        if not self.sale_price:
            return "No sale price yet"
        return f"₹{self.margin:,} a unit · {self.margin_percent}%"

    # -- stock ------------------------------------------------------------

    @property
    def is_out(self):
        return self.quantity <= 0

    @property
    def is_low(self):
        return bool(self.reorder_level and 0 < self.quantity <= self.reorder_level)

    @property
    def stock_state(self):
        if self.is_out:
            return "out of stock"
        if self.is_low:
            return "running low"
        return "in stock"

    @property
    def stock_tone(self):
        return {"out of stock": "red", "running low": "amber"}.get(self.stock_state, "green")

    @property
    def is_reusable(self):
        return self.usage_type == "reusable"

    @property
    def usage_label(self):
        return "Reusable" if self.is_reusable else "Consumable"

    @property
    def reserved_quantity(self):
        """Units held for events right now: still owned, but not free to use."""
        annotated = getattr(self, "reserved_total", None)
        if annotated is not None:
            return annotated
        if self.pk is None:
            return Decimal("0")
        if not hasattr(self, "_reserved_cache"):
            self._reserved_cache = EventItem.reserved_totals([self.pk]).get(
                self.pk, Decimal("0")
            )
        return self._reserved_cache

    @property
    def available_quantity(self):
        """On hand minus what events are holding. Never below zero."""
        return max((self.quantity or Decimal("0")) - self.reserved_quantity, Decimal("0"))

    @property
    def is_unavailable(self):
        return self.available_quantity <= 0

    @property
    def available_label(self):
        return f"{normalise_quantity(self.available_quantity)} {self.unit_label}"

    @property
    def reserved_label(self):
        reserved = self.reserved_quantity
        if not reserved:
            return "Nothing reserved"
        return f"{normalise_quantity(reserved)} reserved for events"

    @property
    def unit_label(self):
        return self.UNIT_SHORT.get(self.unit, self.unit)

    @property
    def quantity_label(self):
        return f"{normalise_quantity(self.quantity)} {self.unit_label}"

    @property
    def reorder_label(self):
        if not self.reorder_level:
            return "No reorder level"
        return f"reorder at {normalise_quantity(self.reorder_level)}"

    @property
    def shortfall(self):
        """How many to buy to get back over the reorder level."""
        if not self.reorder_level:
            return 0
        return max(self.reorder_level - self.quantity, 0)

    @property
    def shortfall_label(self):
        return normalise_quantity(self.shortfall)

    @property
    def restock_cost(self):
        """What it would cost to get back over the reorder level."""
        return int(self.shortfall * self.cost_price)

    @property
    def placeholder_image(self):
        return placeholder(f"stock-{self.pk or self.sku or self.name}", 320, 240)

    @property
    def supplier_name(self):
        return self.supplier.name if self.supplier_id else ""

    @property
    def category_name(self):
        return self.category.name if self.category_id else ""

    @property
    def shelf_label(self):
        return self.location or self.category_name or "Unshelved"

    @property
    def sold_units(self):
        total = self.sale_lines.aggregate(n=models.Sum("quantity"))["n"]
        return normalise_quantity(total or 0)

    def record_movement(self, change, kind="adjustment", **extra):
        """
        The only supported way to move stock. Writes a ledger row, which is
        what actually updates `quantity`.
        """
        return StockMovement.objects.create(
            item=self, kind=kind, change=Decimal(str(change)), **extra
        )


class StockMovementQuerySet(models.QuerySet):
    def incoming(self):
        return self.filter(change__gt=0)

    def outgoing(self):
        return self.filter(change__lt=0)


class StockMovement(models.Model):
    """
    One line of the stock ledger — every unit that ever came in or went out,
    and why. Rows are never edited: a mistake is corrected with a new movement,
    which is what keeps the history worth reading.
    """

    KIND_CHOICES = [
        ("opening", "Opening balance"),
        ("purchase", "Purchase in"),
        ("sale", "Counter sale"),
        ("return_in", "Customer return"),
        ("return_out", "Returned to supplier"),
        ("event", "Used on a booking or event"),
        ("damage", "Damaged"),
        ("lost", "Lost"),
        ("adjustment", "Stock count adjustment"),
        ("reserve", "Reserved for an event"),
        ("event_return", "Back from an event"),
        ("release", "Reservation released"),
    ]
    #: Written by events alone. They move a reservation, not the shelf count,
    #: so typing one into the ledger form by hand would mean nothing.
    EVENT_ONLY_KINDS = ("reserve", "event_return", "release")
    #: Which way each reason normally moves stock. The form reads a plain
    #: quantity as a signed change with this, so nobody has to type a minus.
    DIRECTIONS = {
        "opening": 1,
        "purchase": 1,
        "return_in": 1,
        "sale": -1,
        "return_out": -1,
        "event": -1,
        "damage": -1,
        "lost": -1,
        "adjustment": 0,  # signed by hand — a count can go either way
        "reserve": 0,
        "event_return": 0,
        "release": 0,
    }
    KIND_TONES = {
        "opening": "grey",
        "purchase": "green",
        "sale": "blue",
        "return_in": "violet",
        "return_out": "amber",
        "event": "violet",
        "damage": "red",
        "lost": "red",
        "adjustment": "grey",
        "reserve": "blue",
        "event_return": "green",
        "release": "grey",
    }

    item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name="movements"
    )
    kind = models.CharField(
        max_length=12,
        choices=KIND_CHOICES,
        default="purchase",
        db_index=True,
        verbose_name="Reason",
    )
    change = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Quantity",
        help_text="How many units moved. A negative number takes stock out.",
    )
    held_change = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        verbose_name="Reserved change",
        help_text=(
            "Units put on hold for an event (+) or let go again (−). A hold "
            "never changes the shelf count, only what is free to use."
        ),
    )
    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        verbose_name="Stock after",
    )
    unit_cost = models.PositiveIntegerField(
        default=0, help_text="What one unit cost on this movement (₹). Purchases mostly."
    )
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="movements",
    )
    sale = models.ForeignKey(
        "CounterSale", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="movements", editable=False,
    )
    booking = models.ForeignKey(
        Booking, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stock_movements",
        help_text="If this stock went out on a job, which one.",
    )
    event = models.ForeignKey(
        "Event", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stock_movements", editable=False,
    )
    reference = models.CharField(
        max_length=40, blank=True, help_text="Invoice or delivery-note number."
    )
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="stock_movements", editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = StockMovementQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Stock movement"
        verbose_name_plural = "Stock ledger"

    def __str__(self):
        return f"{self.item} {self.signed_label}"

    def save(self, *args, **kwargs):
        """
        Applying the change and writing the row are one step, under a lock on
        the item, so two people receiving stock at once cannot lose a count.
        """
        if self.pk:
            # The ledger is append-only; an edit would silently un-move stock.
            return super().save(*args, **kwargs)

        with transaction.atomic():
            item = InventoryItem.objects.select_for_update().get(pk=self.item_id)
            item.quantity = (item.quantity or Decimal("0")) + self.change
            item.save(update_fields=["quantity", "updated_at"])
            self.balance_after = item.quantity
            super().save(*args, **kwargs)
            # The caller's copy would otherwise still show the old count.
            self.item.quantity = item.quantity
        return None

    @property
    def is_incoming(self):
        return self.change > 0

    @property
    def delta_state(self):
        """in, out, or hold — a reservation that moved no stock."""
        if self.change > 0:
            return "in"
        if self.change < 0:
            return "out"
        return "hold"

    @property
    def signed_label(self):
        if not self.change and self.held_change:
            verb = "reserved" if self.held_change > 0 else "released"
            return f"{normalise_quantity(abs(self.held_change))} {verb}"
        if not self.change:
            return "0"
        sign = "+" if self.change > 0 else "−"
        return f"{sign}{normalise_quantity(abs(self.change))}"

    @property
    def balance_label(self):
        return f"{normalise_quantity(self.balance_after)} left"

    @property
    def kind_tone(self):
        return self.KIND_TONES.get(self.kind, "grey")

    @property
    def value(self):
        """What the movement was worth, at the cost recorded on it."""
        return int(abs(self.change) * self.unit_cost)

    @property
    def source_label(self):
        if self.sale_id:
            return self.sale.reference
        if self.event_id:
            return self.event.number or self.reference or "—"
        if self.booking_id:
            return self.booking.reference
        if self.supplier_id:
            return self.supplier.name
        return self.reference or "—"

    @property
    def by_label(self):
        if not self.created_by_id:
            return "system"
        return self.created_by.get_full_name() or self.created_by.get_username()


class CounterSaleQuerySet(models.QuerySet):
    def completed(self):
        return self.filter(status="completed")

    def earning(self):
        """Rows that count towards takings — a refund cancels itself out."""
        return self.filter(status="completed")

    def on(self, day):
        return self.filter(sold_at__date=day)


class CounterSale(Timestamped):
    """
    A walk-in sale rung up at the counter.

    Totals are stored rather than derived, so a receipt reprinted next year
    still says what the customer actually paid, whatever the price list has
    done in the meantime.
    """

    STATUS_CHOICES = [
        ("completed", "Completed"),
        ("refunded", "Refunded"),
    ]
    PAYMENT_CHOICES = [
        ("cash", "Cash"),
        ("upi", "UPI"),
        ("card", "Card"),
        ("bank", "Bank transfer"),
        ("credit", "On account"),
    ]

    reference = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    customer_name = models.CharField(
        max_length=120, blank=True, help_text="Optional — a walk-in needs no name."
    )
    phone = models.CharField(max_length=40, blank=True)

    sold_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Sold")
    served_by = models.ForeignKey(
        StaffMember, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="counter_sales", verbose_name="Sold by",
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="counter_sales", editable=False,
    )

    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_CHOICES, default="cash", verbose_name="Paid by"
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="completed", db_index=True
    )

    subtotal = models.PositiveIntegerField(default=0, editable=False)
    discount = models.PositiveIntegerField(default=0, help_text="Flat ₹ off the whole sale.")
    tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name="Tax %",
        help_text="GST or similar, applied after the discount. 0 for none.",
    )
    tax_amount = models.PositiveIntegerField(default=0, editable=False)
    total = models.PositiveIntegerField(default=0, editable=False)
    amount_tendered = models.PositiveIntegerField(
        default=0,
        verbose_name="Cash taken",
        help_text="What the customer handed over, for the change line on the receipt.",
    )
    cost_total = models.PositiveIntegerField(default=0, editable=False)

    notes = models.TextField(blank=True)
    stock_applied = models.BooleanField(default=False, editable=False)

    objects = CounterSaleQuerySet.as_manager()

    class Meta:
        ordering = ["-sold_at", "-id"]
        verbose_name = "Counter sale"
        verbose_name_plural = "Counter sales"

    def __str__(self):
        return f"{self.reference} · ₹{self.total:,}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._next_reference()
        return super().save(*args, **kwargs)

    @staticmethod
    def _next_reference():
        last = CounterSale.objects.order_by("-id").values_list("id", flat=True).first() or 0
        return f"CS-{1000 + last + 1}"

    # -- totals -----------------------------------------------------------

    def recalculate(self, commit=True):
        """Add the lines up. Called once the lines are attached, not before."""
        lines = list(self.lines.all())
        self.subtotal = sum(line.line_total for line in lines)
        self.cost_total = sum(line.line_cost for line in lines)
        net = max(self.subtotal - self.discount, 0)
        self.tax_amount = int(round(net * float(self.tax_percent) / 100))
        self.total = net + self.tax_amount
        if commit:
            self.save(update_fields=[
                "subtotal", "cost_total", "tax_amount", "total", "updated_at",
            ])
        return self.total

    @property
    def profit(self):
        return self.total - self.tax_amount - self.cost_total

    @property
    def margin_percent(self):
        net = self.total - self.tax_amount
        return round(self.profit * 100 / net) if net else 0

    @property
    def change_due(self):
        return max(self.amount_tendered - self.total, 0)

    @property
    def line_count(self):
        # len() rather than .count(), so a prefetched list page stays one query.
        return len(self.lines.all())

    @property
    def item_count(self):
        total = sum((line.quantity for line in self.lines.all()), Decimal("0"))
        return normalise_quantity(total)

    @property
    def items_label(self):
        count = self.line_count
        return f"{count} line{'s' if count != 1 else ''} · {self.item_count} units"

    @property
    def customer_label(self):
        return self.customer_name or "Walk-in"

    @property
    def served_label(self):
        if self.served_by_id:
            return self.served_by.name
        if self.cashier_id:
            return self.cashier.get_full_name() or self.cashier.get_username()
        return "—"

    @property
    def is_refunded(self):
        return self.status == "refunded"

    @property
    def sold_label(self):
        return timezone.localtime(self.sold_at).strftime("%d %b, %H:%M")

    # -- stock ------------------------------------------------------------

    def apply_stock(self, user=None):
        """Take the sold units off the shelf. Safe to call twice — it won't double up."""
        if self.stock_applied:
            return 0
        moved = 0
        for line in self.lines.select_related("item"):
            if line.item_id is None:
                continue
            StockMovement.objects.create(
                item=line.item,
                kind="sale",
                change=-line.quantity,
                unit_cost=line.unit_cost,
                sale=self,
                reference=self.reference,
                note=f"Counter sale to {self.customer_label}",
                created_by=user,
            )
            moved += 1
        CounterSale.objects.filter(pk=self.pk).update(stock_applied=True)
        self.stock_applied = True
        return moved

    def refund(self, user=None, note=""):
        """Reverse the sale: the stock goes back, the row stays for the record."""
        if self.is_refunded:
            return 0
        returned = 0
        if self.stock_applied:
            for line in self.lines.select_related("item"):
                if line.item_id is None:
                    continue
                StockMovement.objects.create(
                    item=line.item,
                    kind="return_in",
                    change=line.quantity,
                    unit_cost=line.unit_cost,
                    sale=self,
                    reference=self.reference,
                    note=note or f"Refund of {self.reference}",
                    created_by=user,
                )
                returned += 1
        self.status = "refunded"
        self.stock_applied = False
        self.save(update_fields=["status", "stock_applied", "updated_at"])
        return returned


class CounterSaleLine(models.Model):
    """
    One line on a receipt. Name, price and cost are copied off the item as it
    was sold, so the receipt survives a rename, a repricing or a deletion.
    """

    sale = models.ForeignKey(CounterSale, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(
        InventoryItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sale_lines",
    )
    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=32, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.PositiveIntegerField(default=0)
    unit_cost = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["id"]
        verbose_name = "Sale line"

    def __str__(self):
        return f"{self.name} × {normalise_quantity(self.quantity)}"

    def save(self, *args, **kwargs):
        # Snapshot whatever the item says today, once.
        if self.item_id and not self.name:
            self.name = self.item.name
            self.sku = self.item.sku
            if not self.unit_price:
                self.unit_price = self.item.sale_price
            if not self.unit_cost:
                self.unit_cost = self.item.cost_price
        return super().save(*args, **kwargs)

    @property
    def line_total(self):
        return int(round(self.quantity * self.unit_price))

    @property
    def line_cost(self):
        return int(round(self.quantity * self.unit_cost))

    @property
    def line_profit(self):
        return self.line_total - self.line_cost

    @property
    def quantity_label(self):
        return normalise_quantity(self.quantity)


# ---------------------------------------------------------------------------
# Events — who they are for, what they need, what they cost, what is paid
# ---------------------------------------------------------------------------
#
# Stock and events meet in exactly one idea: a *hold*. Reserving 30 chairs for
# an event does not take them off the shelf — `InventoryItem.quantity` stays
# at 100 — it holds them, so only 70 are free for anything else. What happens
# afterwards decides whether the shelf count moves:
#
#     reusable    reserve → returned            the hold ends, count untouched
#                         → damaged / lost      the hold ends, count goes down
#     consumable  reserve → consumed            the hold ends, count goes down
#                         → returned (unused)   the hold ends, count untouched
#     external    never touches stock at all
#
# Every one of those steps writes a StockMovement, so the ledger reads as the
# event's story ("30 × Chair reserved for EVT-00001"). A hold is recorded in
# `held_change` with a `change` of zero. What an event is holding right now is
# never stored as a total anywhere; it is always worked out from the lines, so
# it cannot drift.
#
# Every change to a hold locks the stock item rows first (in pk order), then
# the event lines, so two people reserving the last units at the same moment
# queue behind each other instead of both succeeding.


def _whole(value):
    return value == value.to_integral_value()


def _units(value):
    return normalise_quantity(value)


class Customer(Timestamped):
    """
    Somebody the company runs events for. Website bookings still carry their
    own name and phone; an event points at one of these, so a repeat customer's
    history lives in one place.
    """

    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} · {self.phone}" if self.phone else self.name

    @property
    def contact_line(self):
        return self.phone or self.email or "No contact on file"

    @property
    def event_total(self):
        annotated = getattr(self, "event_count", None)
        return annotated if annotated is not None else self.events.count()

    @property
    def revenue_total(self):
        """What their events are worth, cancellations left out."""
        annotated = getattr(self, "billed", None)
        if annotated is None:
            annotated = self.events.exclude(status="cancelled").aggregate(
                total=models.Sum("revenue")
            )["total"]
        return int(annotated or 0)


class EventQuerySet(models.QuerySet):
    def live(self):
        return self.exclude(status="cancelled")

    def open(self):
        return self.filter(status__in=Event.OPEN_STATUSES)

    def upcoming(self):
        return self.open().filter(event_date__gte=timezone.localdate())

    def with_paid(self):
        """Annotate `paid_total`, the sum of payments, without a join."""
        paid = (
            EventPayment.objects.filter(event=models.OuterRef("pk"))
            .order_by()
            .values("event")
            .annotate(total=models.Sum("amount"))
            .values("total")
        )
        return self.annotate(
            paid_total=Coalesce(
                models.Subquery(paid, output_field=models.IntegerField()),
                models.Value(0),
                output_field=models.IntegerField(),
            )
        )


class Event(Timestamped):
    """
    One event the company runs: a customer, a date, a place, and a price.
    Its items, expenses and payments hang off it; its profit is worked out
    from them rather than typed in.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("in_progress", "In progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    STATUS_TONES = {
        "draft": "grey",
        "confirmed": "blue",
        "in_progress": "violet",
        "completed": "green",
        "cancelled": "red",
    }
    OPEN_STATUSES = ("draft", "confirmed", "in_progress")
    #: Once confirmed, an inventory line is reserved the moment it is added.
    HOLDING_STATUSES = ("confirmed", "in_progress")
    PAYMENT_STATES = {
        "unpaid": ("Unpaid", "red"),
        "partial": ("Part paid", "amber"),
        "paid": ("Paid in full", "green"),
    }

    number = models.CharField(
        max_length=20, unique=True, null=True, blank=True, editable=False,
        verbose_name="Event number",
    )
    name = models.CharField(max_length=160, verbose_name="Event name")
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="events",
    )
    event_date = models.DateField(db_index=True, verbose_name="Event date")
    location = models.CharField(
        max_length=200, blank=True, help_text="Venue and address — where the crew goes.",
    )
    guests = models.PositiveIntegerField(default=0, verbose_name="Number of guests")
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="draft", db_index=True,
    )
    revenue = models.PositiveIntegerField(
        default=0,
        verbose_name="Revenue",
        help_text="What the customer pays for the whole event (₹).",
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="events_created", editable=False,
    )

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["-event_date", "-id"]

    def __str__(self):
        return f"{self.number} · {self.name}" if self.number else self.name

    def save(self, *args, **kwargs):
        # The number comes from the primary key, so two events created at the
        # same moment can never be handed the same one.
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.number:
            self.number = f"EVT-{self.pk:05d}"
            Event.objects.filter(pk=self.pk).update(number=self.number)

    def get_absolute_url(self):
        return reverse("panel:event_detail", args=[self.pk])

    # -- state ------------------------------------------------------------

    @property
    def status_tone(self):
        return self.STATUS_TONES.get(self.status, "grey")

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_cancelled(self):
        return self.status == "cancelled"

    @property
    def can_change_items(self):
        return self.status in self.OPEN_STATUSES

    @property
    def can_take_money(self):
        return self.status != "cancelled"

    @property
    def can_record_usage(self):
        return self.status in ("in_progress", "completed")

    @property
    def can_delete(self):
        return self.status in ("draft", "cancelled") and not self.has_outstanding

    @property
    def days_away(self):
        return (self.event_date - timezone.localdate()).days

    @property
    def when_label(self):
        days = self.days_away
        if days == 0:
            return "today"
        if days == 1:
            return "tomorrow"
        if days == -1:
            return "yesterday"
        return f"in {days} days" if days > 0 else f"{-days} days ago"

    # -- lines ------------------------------------------------------------
    # Each reads `items.all()`, so a prefetched event costs no extra queries.

    @property
    def inventory_lines(self):
        return [line for line in self.items.all() if line.is_inventory]

    @property
    def external_lines(self):
        return [line for line in self.items.all() if line.is_external]

    @property
    def needs_allocation(self):
        return any(line.unreserved > 0 for line in self.inventory_lines)

    @property
    def outstanding_units(self):
        return sum((line.outstanding for line in self.inventory_lines), Decimal("0"))

    @property
    def has_outstanding(self):
        return self.outstanding_units > 0

    # -- money ------------------------------------------------------------

    @property
    def external_cost(self):
        return sum(line.cost for line in self.external_lines)

    @property
    def inventory_cost(self):
        """Consumables used, plus reusable stock damaged or lost."""
        return sum(line.cost for line in self.inventory_lines)

    @property
    def items_cost(self):
        return sum(line.cost for line in self.items.all())

    @property
    def expenses_total(self):
        return sum(expense.amount for expense in self.expenses.all())

    @property
    def total_cost(self):
        return self.items_cost + self.expenses_total

    @property
    def paid(self):
        annotated = getattr(self, "paid_total", None)
        if annotated is not None:
            return int(annotated)
        return sum(payment.amount for payment in self.payments.all())

    @property
    def remaining(self):
        """Revenue − paid. Negative only if the price dropped after payment."""
        return self.revenue - self.paid

    @property
    def profit(self):
        return self.revenue - self.total_cost

    @property
    def margin_percent(self):
        return round(self.profit * 100 / self.revenue) if self.revenue else 0

    @property
    def paid_percent(self):
        if not self.revenue:
            return 100 if self.paid else 0
        return min(round(self.paid * 100 / self.revenue), 100)

    @property
    def payment_state(self):
        paid = self.paid
        if paid and paid >= self.revenue:
            return "paid"
        if paid:
            return "partial"
        return "unpaid"

    @property
    def payment_label(self):
        return self.PAYMENT_STATES[self.payment_state][0]

    @property
    def payment_tone(self):
        return self.PAYMENT_STATES[self.payment_state][1]

    # -- workflow ---------------------------------------------------------

    def _locked(self):
        """This event's row, locked until the surrounding transaction ends."""
        return Event.objects.select_for_update().get(pk=self.pk)

    def _set_status(self, event, status):
        event.status = status
        event.save(update_fields=["status", "updated_at"])
        self.status = status

    def confirm(self, user=None):
        with transaction.atomic():
            event = self._locked()
            if event.status != "draft":
                raise ValidationError("Only a draft event can be confirmed.")
            self._set_status(event, "confirmed")

    def allocate(self, user=None):
        """Reserve every inventory line up to what it needs. All or nothing."""
        with transaction.atomic():
            event = self._locked()
            if event.status not in self.HOLDING_STATUSES:
                raise ValidationError(
                    "Inventory is reserved once the event is confirmed."
                )
            lines = list(event.items.filter(item_type="inventory"))
            return EventItem.reserve_lines(event, lines, user=user)

    def start(self, user=None):
        with transaction.atomic():
            event = self._locked()
            if event.status != "confirmed":
                raise ValidationError("Only a confirmed event can be started.")
            short = [
                line for line in event.items.filter(item_type="inventory")
                if line.unreserved > 0
            ]
            if short:
                names = ", ".join(
                    f"{line.name} ({_units(line.unreserved)} more)" for line in short[:3]
                )
                raise ValidationError(
                    f"Reserve the inventory before starting — still needed: {names}."
                )
            self._set_status(event, "in_progress")

    def complete(self, user=None):
        with transaction.atomic():
            event = self._locked()
            if event.status != "in_progress":
                raise ValidationError("Only an event in progress can be completed.")
            self._set_status(event, "completed")

    def cancel(self, user=None):
        """Cancel, and hand every unit it was holding back to the shelf."""
        with transaction.atomic():
            event = self._locked()
            if event.status not in self.OPEN_STATUSES:
                raise ValidationError(
                    f"A {event.get_status_display().lower()} event cannot be cancelled."
                )
            released = EventItem.release_lines(event, user=user)
            self._set_status(event, "cancelled")
        return released

    def release_reservations(self, user=None):
        """For a cancelled event that is somehow still holding stock."""
        with transaction.atomic():
            event = self._locked()
            if event.status != "cancelled":
                raise ValidationError("Only a cancelled event releases everything at once.")
            return EventItem.release_lines(event, user=user)

    def finalize_inventory(self, user=None):
        """
        Close the books on stock after the event. Whatever is still out is
        settled the ordinary way — reusable comes back, consumable was used.
        Damage and losses are recorded line by line before this.
        """
        with transaction.atomic():
            event = self._locked()
            if event.status != "completed":
                raise ValidationError("Inventory is finalised once the event is completed.")
            settled = 0
            for line in event.items.filter(item_type="inventory").order_by(
                "inventory_item_id", "pk"
            ):
                if line.outstanding <= 0:
                    continue
                if line.usage_type == "reusable":
                    line.record_usage(returned=line.outstanding, user=user)
                else:
                    line.record_usage(consumed=line.outstanding, user=user)
                settled += 1
            return settled

    def add_inventory_item(self, item, quantity, notes="", user=None):
        """
        Put a stock item on the event, or top up the line it is already on.
        Once confirmed, the extra units are reserved there and then.
        """
        quantity = Decimal(str(quantity))
        with transaction.atomic():
            event = self._locked()
            if event.status not in self.OPEN_STATUSES:
                raise ValidationError(
                    f"Items cannot be added to a {event.get_status_display().lower()} event."
                )
            item = InventoryItem.objects.select_for_update().get(pk=item.pk)
            if not item.is_active:
                raise ValidationError(f"{item.name} has been retired from stock.")
            existing = event.items.filter(item_type="inventory", inventory_item=item).first()
            if existing is not None:
                existing.set_quantity(existing.quantity + quantity, user=user)
                if notes:
                    existing.notes = f"{existing.notes}\n{notes}".strip()
                    existing.save(update_fields=["notes"])
                return existing

            EventItem.check_quantity(item, quantity)
            free = item.quantity - EventItem.reserved_totals([item.pk], lock=True).get(
                item.pk, Decimal("0")
            )
            if quantity > max(free, Decimal("0")):
                raise ValidationError(
                    f"Only {_units(max(free, Decimal('0')))} units are available."
                )
            line = EventItem.objects.create(
                event=event, item_type="inventory", inventory_item=item,
                quantity=quantity, notes=notes,
            )
            if event.status in self.HOLDING_STATUSES:
                EventItem.reserve_lines(event, [line], user=user)
            return line

    def add_inventory_items(self, entries, user=None):
        """
        Several stock items in one go, as [(item, quantity), ...]. Every
        shortfall is checked first and reported together; either all of them
        are added or none are.
        """
        wanted = {}
        for item, quantity in entries:
            quantity = Decimal(str(quantity))
            if item.pk in wanted:
                wanted[item.pk] = (wanted[item.pk][0], wanted[item.pk][1] + quantity)
            else:
                wanted[item.pk] = (item, quantity)
        if not wanted:
            raise ValidationError("Pick at least one stock item.")

        with transaction.atomic():
            event = self._locked()
            if event.status not in self.OPEN_STATUSES:
                raise ValidationError(
                    f"Items cannot be added to a {event.get_status_display().lower()} event."
                )
            items = EventItem._lock_items(wanted.keys())
            held = EventItem.reserved_totals(items.keys(), lock=True)
            existing = {
                line.inventory_item_id: line
                for line in event.items.select_for_update().filter(
                    item_type="inventory", inventory_item_id__in=list(items.keys())
                )
            }

            problems = []
            for pk, (_item, quantity) in wanted.items():
                item = items.get(pk)
                if item is None or not item.is_active:
                    problems.append(f"{_item.name} has been retired from stock.")
                    continue
                try:
                    EventItem.check_quantity(item, quantity)
                except ValidationError as error:
                    problems.extend(error.messages)
                    continue
                # What still has to come off the free pile: the new units, plus
                # whatever this event's line already needs but does not hold.
                line = existing.get(pk)
                need = quantity + (line.unreserved if line is not None else Decimal("0"))
                free = max(item.quantity - held.get(pk, Decimal("0")), Decimal("0"))
                if need > free:
                    problems.append(
                        f"Only {_units(free)} units of {item.name} are available "
                        f"(this needs {_units(need)})."
                    )
            if problems:
                raise ValidationError(problems)

            return [
                event.add_inventory_item(items[pk], quantity, user=user)
                for pk, (_item, quantity) in wanted.items()
            ]


class EventItem(PictureMixin, models.Model):
    """
    One thing an event needs. Either a stock item — reserved, then returned or
    used up — or something arranged outside, which never goes near stock.

    For stock lines the five quantities tell the whole story:
    `reserved_qty` is what was put on hold, and returned + consumed + damaged +
    lost is what has been settled since. The difference is still out.

    The picture fields are for external items; a stock line shows the stock
    item's own picture.
    """

    TYPE_CHOICES = [
        ("inventory", "Inventory item"),
        ("external", "External item"),
    ]
    SETTLED_FIELDS = ("returned_qty", "consumed_qty", "damaged_qty", "lost_qty")

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(
        max_length=10, choices=TYPE_CHOICES, default="inventory", db_index=True,
    )
    inventory_item = models.ForeignKey(
        InventoryItem, null=True, blank=True, on_delete=models.PROTECT,
        related_name="event_lines", verbose_name="Stock item",
    )
    name = models.CharField(max_length=120, verbose_name="Item name")
    usage_type = models.CharField(
        max_length=12, choices=InventoryItem.USAGE_CHOICES, blank=True, editable=False,
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=1,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit_cost = models.PositiveIntegerField(
        default=0, verbose_name="Unit cost", help_text="What one costs (₹).",
    )
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="event_items", verbose_name="Supplier",
    )
    vendor = models.CharField(
        max_length=120, blank=True, verbose_name="…or vendor name",
        help_text="For a one-off vendor who is not in your supplier list.",
    )
    notes = models.TextField(blank=True)

    reserved_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    returned_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    consumed_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    damaged_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    lost_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["item_type", "id"]
        verbose_name = "Event item"

    def __str__(self):
        return f"{self.name} × {_units(self.quantity)}"

    def save(self, *args, **kwargs):
        # A stock line snapshots the item as it was added, so renaming or
        # repricing the item later does not rewrite a past event's cost.
        if self.item_type == "inventory" and self.inventory_item_id and not self.name:
            item = self.inventory_item
            self.name = item.name
            self.usage_type = item.usage_type
            if not self.unit_cost:
                self.unit_cost = item.cost_price
        if self.item_type == "external":
            self.inventory_item = None
            self.usage_type = ""
        return super().save(*args, **kwargs)

    # -- what it is -------------------------------------------------------

    @property
    def is_inventory(self):
        return self.item_type == "inventory"

    @property
    def is_external(self):
        return self.item_type == "external"

    @property
    def is_reusable(self):
        return self.is_inventory and self.usage_type == "reusable"

    @property
    def type_label(self):
        if self.is_external:
            return "External"
        return "Reusable stock" if self.is_reusable else "Consumable stock"

    @property
    def type_tone(self):
        if self.is_external:
            return "amber"
        return "blue" if self.is_reusable else "violet"

    @property
    def unit_label(self):
        if self.is_inventory and self.inventory_item_id:
            return self.inventory_item.unit_label
        return ""

    @property
    def vendor_label(self):
        if self.supplier_id:
            return self.supplier.name
        return self.vendor

    @property
    def picture(self):
        """A real picture of the thing, or "" — never a stand-in photo."""
        if self.is_inventory and self.inventory_item_id:
            item = self.inventory_item
            return item.image if item.has_own_image else ""
        return self.image if self.has_own_image else ""

    # -- quantities -------------------------------------------------------

    @staticmethod
    def outstanding_expression():
        F = models.F
        return (
            F("reserved_qty") - F("returned_qty") - F("consumed_qty")
            - F("damaged_qty") - F("lost_qty")
        )

    @property
    def settled_qty(self):
        return self.returned_qty + self.consumed_qty + self.damaged_qty + self.lost_qty

    @property
    def outstanding(self):
        """Held right now: reserved and not yet returned or used."""
        return self.reserved_qty - self.settled_qty

    @property
    def unreserved(self):
        """Still to reserve before the event has everything it needs."""
        if self.is_external:
            return Decimal("0")
        return max(self.quantity - self.reserved_qty, Decimal("0"))

    @property
    def quantity_label(self):
        return _units(self.quantity)

    @property
    def meter(self):
        """The stock bar: each state as a share of what the event needs."""
        base = max(self.quantity, self.reserved_qty)
        if not self.is_inventory or base <= 0:
            return []
        out_label = (
            "Out at the event" if self.event.status in ("in_progress", "completed")
            else "Reserved"
        )
        rows = [
            ("returned", "Returned", self.returned_qty),
            ("consumed", "Consumed", self.consumed_qty),
            ("damaged", "Damaged", self.damaged_qty),
            ("lost", "Lost", self.lost_qty),
            ("out", out_label, self.outstanding),
            ("todo", "Not reserved", self.unreserved),
        ]
        return [
            {"key": key, "label": label, "value": _units(value),
             "pct": f"{value * 100 / base:.2f}"}
            for key, label, value in rows if value > 0
        ]

    # -- money ------------------------------------------------------------

    @property
    def cost_quantity(self):
        """
        How many units count towards the event's cost.

        External: all of them. Reusable stock: only what was damaged or lost,
        because the rest came back. Consumable stock: what was planned, less
        whatever came back unused — and on a cancelled event, only what was
        actually used.
        """
        if self.is_external:
            return self.quantity
        if self.is_reusable:
            return self.damaged_qty + self.lost_qty
        if self.event.status == "cancelled":
            return self.consumed_qty + self.damaged_qty + self.lost_qty
        return max(self.quantity - self.returned_qty, Decimal("0"))

    @property
    def cost(self):
        return int(round(self.cost_quantity * self.unit_cost))

    @property
    def cost_note(self):
        if self.is_reusable:
            if self.cost:
                return f"{_units(self.cost_quantity)} written off at ₹{self.unit_cost:,}"
            return "Comes back to stock"
        return f"{_units(self.cost_quantity)} × ₹{self.unit_cost:,}"

    # -- what the line is doing -------------------------------------------

    @property
    def state(self):
        """(label, tone) for the status column."""
        status = self.event.status
        if self.is_external:
            return ("Cancelled", "grey") if status == "cancelled" else ("Arranged", "amber")
        if self.outstanding > 0:
            if self.unreserved > 0 and status != "cancelled":
                return ("Part reserved", "amber")
            if status in ("in_progress", "completed"):
                return ("Out at the event", "violet") if self.is_reusable else ("Issued", "violet")
            return ("Reserved", "blue")
        if self.settled_qty > 0:
            if self.unreserved > 0 and status in Event.HOLDING_STATUSES:
                return ("Part reserved", "amber")
            if self.is_reusable:
                if self.damaged_qty or self.lost_qty:
                    return ("Back, with losses", "amber")
                return ("Returned", "green")
            return ("Consumed", "green") if self.consumed_qty else ("Returned unused", "green")
        if status == "cancelled":
            return ("Released", "grey")
        if status == "draft":
            return ("Planned", "grey")
        if status == "completed":
            return ("Never reserved", "grey")
        return ("Not reserved", "red")

    @property
    def state_label(self):
        return self.state[0]

    @property
    def state_tone(self):
        return self.state[1]

    # -- the stock side ---------------------------------------------------

    @staticmethod
    def check_quantity(item, quantity):
        if quantity <= 0:
            raise ValidationError("The quantity has to be more than zero.")
        if item.is_reusable and not _whole(quantity):
            raise ValidationError(
                f"{item.name} is reusable stock, so it is counted in whole units."
            )

    @classmethod
    def reserved_totals(cls, item_ids, lock=False):
        """{item pk: units held across every event}. `lock` for the write paths."""
        rows = cls.objects.filter(
            item_type="inventory", inventory_item_id__in=list(item_ids)
        )
        if lock:
            rows = rows.select_for_update()
        totals = defaultdict(lambda: Decimal("0"))
        for line in rows.only(
            "inventory_item_id", "reserved_qty", *cls.SETTLED_FIELDS
        ):
            totals[line.inventory_item_id] += line.outstanding
        return dict(totals)

    @staticmethod
    def _lock_items(item_ids):
        return {
            item.pk: item
            for item in InventoryItem.objects.select_for_update()
            .filter(pk__in=sorted(set(item_ids)))
            .order_by("pk")
        }

    def _log(self, event, item, kind, user, note, change=Decimal("0"), held=Decimal("0")):
        return StockMovement.objects.create(
            item=item,
            kind=kind,
            change=change,
            held_change=held,
            unit_cost=self.unit_cost,
            event=event,
            reference=event.number or "",
            note=note[:200],
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

    @classmethod
    def reserve_lines(cls, event, lines, user=None):
        """
        Reserve whatever each line still needs. Checks every line first and
        raises one error naming all the shortfalls, so nothing is half-done.
        """
        lines = [line for line in lines if line.is_inventory]
        if not lines:
            return 0
        items = cls._lock_items(line.inventory_item_id for line in lines)
        held = cls.reserved_totals(items.keys(), lock=True)
        fresh = list(
            cls.objects.select_for_update()
            .filter(pk__in=[line.pk for line in lines])
            .order_by("inventory_item_id", "pk")
        )

        wanted = defaultdict(lambda: Decimal("0"))
        for line in fresh:
            wanted[line.inventory_item_id] += line.unreserved

        problems = []
        for item_id, need in wanted.items():
            if need <= 0:
                continue
            item = items[item_id]
            free = max(item.quantity - held.get(item_id, Decimal("0")), Decimal("0"))
            if need > free:
                problems.append(
                    f"Only {_units(free)} units of {item.name} are available "
                    f"(this needs {_units(need)})."
                )
        if problems:
            raise ValidationError(problems)

        reserved = 0
        for line in fresh:
            need = line.unreserved
            if need <= 0:
                continue
            item = items[line.inventory_item_id]
            line.reserved_qty += need
            line.save(update_fields=["reserved_qty"])
            line._log(
                event, item, "reserve", user, held=need,
                note=f"{_units(need)} × {item.name} reserved for {event.number}",
            )
            reserved += 1
        return reserved

    @classmethod
    def release_lines(cls, event, user=None):
        """Let go of everything the event's lines are still holding."""
        lines = list(event.items.filter(item_type="inventory"))
        if not lines:
            return 0
        items = cls._lock_items(line.inventory_item_id for line in lines)
        released = 0
        for line in cls.objects.select_for_update().filter(
            pk__in=[line.pk for line in lines]
        ).order_by("inventory_item_id", "pk"):
            amount = line.outstanding
            if amount <= 0:
                continue
            line._release(event, items[line.inventory_item_id], amount, user)
            released += 1
        return released

    def _release(self, event, item, amount, user):
        self.reserved_qty -= amount
        self.save(update_fields=["reserved_qty"])
        self._log(
            event, item, "release", user, held=-amount,
            note=f"{_units(amount)} × {item.name} released from {event.number}",
        )

    def set_quantity(self, quantity, user=None):
        """
        Change how many the event needs. Going down lets go of the surplus
        straight away; going up on a confirmed event reserves the extra.
        """
        quantity = Decimal(str(quantity))
        if not self.is_inventory:
            raise ValidationError("Only stock lines are reserved.")
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.event_id)
            if event.status not in Event.OPEN_STATUSES:
                raise ValidationError(
                    f"A {event.get_status_display().lower()} event's items are fixed."
                )
            item = self._lock_items([self.inventory_item_id])[self.inventory_item_id]
            line = EventItem.objects.select_for_update().get(pk=self.pk)
            EventItem.check_quantity(item, quantity)
            if quantity < line.settled_qty:
                raise ValidationError(
                    f"{_units(line.settled_qty)} have already come back or been used, "
                    "so the quantity cannot go below that."
                )
            if event.status == "draft" and quantity > line.quantity:
                free = item.quantity - EventItem.reserved_totals([item.pk], lock=True).get(
                    item.pk, Decimal("0")
                )
                if quantity > max(free, Decimal("0")):
                    raise ValidationError(
                        f"Only {_units(max(free, Decimal('0')))} units are available."
                    )
            line.quantity = quantity
            line.save(update_fields=["quantity"])
            if line.reserved_qty > quantity:
                line._release(event, item, line.reserved_qty - quantity, user)
            elif event.status in Event.HOLDING_STATUSES and quantity > line.reserved_qty:
                EventItem.reserve_lines(event, [line], user=user)
            self.quantity = quantity
            self.refresh_from_db()

    def remove(self, user=None):
        """Take the line off the event, releasing its hold first."""
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.event_id)
            if event.status not in Event.OPEN_STATUSES:
                raise ValidationError(
                    f"A {event.get_status_display().lower()} event's items are fixed."
                )
            if self.is_inventory:
                item = self._lock_items([self.inventory_item_id])[self.inventory_item_id]
                line = EventItem.objects.select_for_update().get(pk=self.pk)
                if line.settled_qty > 0:
                    raise ValidationError(
                        "Returns or usage are already recorded against this line, "
                        "so it stays on the event as a record."
                    )
                if line.outstanding > 0:
                    line._release(event, item, line.outstanding, user)
            self.delete()

    def record_usage(self, returned=0, consumed=0, damaged=0, lost=0, user=None):
        """
        Settle some of what is still out. Returned units simply stop being
        held; consumed, damaged and lost units come off the shelf for good.
        """
        amounts = {
            "returned": Decimal(str(returned or 0)),
            "consumed": Decimal(str(consumed or 0)),
            "damaged": Decimal(str(damaged or 0)),
            "lost": Decimal(str(lost or 0)),
        }
        if not self.is_inventory:
            raise ValidationError("External items never touch stock.")
        if any(value < 0 for value in amounts.values()):
            raise ValidationError("Quantities cannot be negative.")
        total = sum(amounts.values())
        if total <= 0:
            raise ValidationError("Enter how many came back or were used.")

        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.event_id)
            if event.status not in ("in_progress", "completed"):
                raise ValidationError(
                    "Returns and usage are recorded once the event has started."
                )
            item = self._lock_items([self.inventory_item_id])[self.inventory_item_id]
            line = EventItem.objects.select_for_update().get(pk=self.pk)

            if line.usage_type == "reusable":
                if amounts["consumed"]:
                    raise ValidationError(
                        "Reusable stock is not consumed — record it as returned, damaged or lost."
                    )
                if not all(_whole(value) for value in amounts.values()):
                    raise ValidationError("Reusable stock is counted in whole units.")
            elif amounts["damaged"] or amounts["lost"]:
                raise ValidationError(
                    "Consumable stock is either consumed or returned unused."
                )

            if total > line.outstanding:
                raise ValidationError(
                    f"Only {_units(line.outstanding)} {item.unit_label} of {item.name} "
                    "are still out on this event."
                )
            permanent = amounts["consumed"] + amounts["damaged"] + amounts["lost"]
            if permanent > item.quantity:
                raise ValidationError(
                    f"The shelf only has {item.quantity_label} of {item.name} left, "
                    "so that would take stock below zero. Check the stock ledger."
                )

            line.returned_qty += amounts["returned"]
            line.consumed_qty += amounts["consumed"]
            line.damaged_qty += amounts["damaged"]
            line.lost_qty += amounts["lost"]
            line.save(update_fields=list(self.SETTLED_FIELDS))

            number = event.number
            if amounts["returned"]:
                n = amounts["returned"]
                line._log(event, item, "event_return", user, held=-n,
                          note=f"{_units(n)} × {item.name} returned from {number}")
            if amounts["consumed"]:
                n = amounts["consumed"]
                line._log(event, item, "event", user, change=-n, held=-n,
                          note=f"{_units(n)} × {item.name} consumed at {number}")
            if amounts["damaged"]:
                n = amounts["damaged"]
                line._log(event, item, "damage", user, change=-n, held=-n,
                          note=f"{_units(n)} × {item.name} damaged in {number}")
            if amounts["lost"]:
                n = amounts["lost"]
                line._log(event, item, "lost", user, change=-n, held=-n,
                          note=f"{_units(n)} × {item.name} lost at {number}")

            for name in self.SETTLED_FIELDS:
                setattr(self, name, getattr(line, name))
        return total


class EventExpense(models.Model):
    """Money spent to run an event that is not an item: the van, the venue, the crew."""

    CATEGORY_CHOICES = [
        ("transport", "Transportation"),
        ("venue", "Venue"),
        ("staff", "Staff"),
        ("decoration", "Decoration"),
        ("food", "Food"),
        ("fuel", "Fuel"),
        ("other", "Other"),
    ]
    CATEGORY_TONES = {
        "transport": "blue",
        "venue": "violet",
        "staff": "green",
        "decoration": "amber",
        "food": "red",
        "fuel": "grey",
        "other": "grey",
    }

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="expenses")
    name = models.CharField(max_length=120, verbose_name="Expense")
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default="other")
    amount = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], help_text="In ₹.",
    )
    spent_on = models.DateField(default=timezone.localdate, verbose_name="Date")
    notes = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="event_expenses", editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-spent_on", "-id"]
        verbose_name = "Event expense"

    def __str__(self):
        return f"{self.name} · ₹{self.amount:,}"

    @property
    def category_tone(self):
        return self.CATEGORY_TONES.get(self.category, "grey")


class EventPayment(models.Model):
    """Money in from the customer against an event. Several make up the total."""

    METHOD_CHOICES = [
        ("cash", "Cash"),
        ("upi", "UPI"),
        ("bank", "Bank transfer"),
        ("card", "Card"),
        ("cheque", "Cheque"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="payments")
    paid_on = models.DateField(default=timezone.localdate, verbose_name="Date")
    amount = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], help_text="In ₹.",
    )
    method = models.CharField(
        max_length=10, choices=METHOD_CHOICES, default="cash", verbose_name="Paid by",
    )
    reference = models.CharField(
        max_length=60, blank=True, help_text="UTR, cheque number or receipt number.",
    )
    notes = models.CharField(max_length=240, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="event_payments", editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-id"]
        verbose_name = "Event payment"

    def __str__(self):
        return f"₹{self.amount:,} on {self.paid_on:%d %b %Y}"


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
        verbose_name = "Panel account"
        verbose_name_plural = "Panel accounts"

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
    def staff_member(self):
        """The operational staff record this login is linked to, if any."""
        return getattr(self.user, "staff_member", None)

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
    staff_member = models.ForeignKey(
        "StaffMember",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invites",
        verbose_name="For which staff member",
        help_text="Optional. Whoever signs up with this code is linked to that staff record.",
    )
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
