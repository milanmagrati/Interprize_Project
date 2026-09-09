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

from collections import namedtuple
from decimal import Decimal

from django.conf import settings
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models, transaction
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
        ("event", "Used on a booking"),
        ("damage", "Damaged or lost"),
        ("adjustment", "Stock count adjustment"),
    ]
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
        "adjustment": 0,  # signed by hand — a count can go either way
    }
    KIND_TONES = {
        "opening": "grey",
        "purchase": "green",
        "sale": "blue",
        "return_in": "violet",
        "return_out": "amber",
        "event": "violet",
        "damage": "red",
        "adjustment": "grey",
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
    def signed_label(self):
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
