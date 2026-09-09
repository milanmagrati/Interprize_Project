"""
Django's built-in admin.

The staff-facing tool is the control panel at /manage/; this exists for the
cases it deliberately does not cover — repairing a bad row, inspecting
permissions, working during a template error. Registrations are deliberately
plain.
"""

from django.contrib import admin

from . import models


class PackageImageInline(admin.TabularInline):
    model = models.PackageImage
    extra = 0


@admin.register(models.Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "price", "is_featured", "is_active")
    list_filter = ("category", "is_featured", "is_active")
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [PackageImageInline]


@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "price_from", "position", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(models.HeroSlide)
class HeroSlideAdmin(admin.ModelAdmin):
    list_display = ("eyebrow", "heading", "media_type", "position", "is_active")
    list_filter = ("media_type", "is_active")


@admin.register(models.Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("reference", "customer_name", "event_date", "status", "amount")
    list_filter = ("status", "payment_status", "city")
    search_fields = ("reference", "customer_name", "phone", "email")
    date_hierarchy = "event_date"


@admin.register(models.Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "occasion", "status", "created_at")
    list_filter = ("status",)


@admin.register(models.StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "last_seen")
    list_filter = ("role",)


@admin.register(models.StaffCategory)
class StaffCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "position", "is_active")
    list_filter = ("kind", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(models.StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "employment", "city", "account", "is_active")
    list_filter = ("category", "employment", "is_verified", "is_active")
    search_fields = ("name", "phone", "email", "skills")


class CounterSaleLineInline(admin.TabularInline):
    model = models.CounterSaleLine
    extra = 0


@admin.register(models.InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "quantity", "cost_price", "sale_price", "is_active")
    list_filter = ("category", "supplier", "unit", "is_sellable", "is_active")
    search_fields = ("name", "sku", "barcode", "location")
    readonly_fields = ("quantity",)


@admin.register(models.StockCategory)
class StockCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "position", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(models.Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "lead_time_days", "is_active")
    search_fields = ("name", "contact_name", "phone", "email")


@admin.register(models.StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "item", "kind", "change", "balance_after", "created_by")
    list_filter = ("kind",)
    search_fields = ("item__name", "item__sku", "reference", "note")
    date_hierarchy = "created_at"


@admin.register(models.CounterSale)
class CounterSaleAdmin(admin.ModelAdmin):
    list_display = ("reference", "sold_at", "customer_name", "total", "payment_method", "status")
    list_filter = ("status", "payment_method")
    search_fields = ("reference", "customer_name", "phone")
    date_hierarchy = "sold_at"
    inlines = [CounterSaleLineInline]


@admin.register(models.InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "role", "used_by", "created_at")


@admin.register(models.ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "model_label", "object_label")
    list_filter = ("action",)


for model in (
    models.SiteSettings, models.NavLink, models.TrustBadge, models.City,
    models.Testimonial, models.FAQ, models.Feature, models.HowItWorksStep,
    models.PricingRow, models.TimeSlot, models.AddOn,
    models.Coupon, models.PackageImage,
):
    admin.site.register(model)
