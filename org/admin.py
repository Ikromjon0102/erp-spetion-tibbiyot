from django.contrib import admin

from .models import Branch, Organization


class BranchInline(admin.TabularInline):
    model = Branch
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'brand_color', 'meals_enabled', 'expenses_enabled', 'is_active')
    inlines = [BranchInline]


admin.site.register(Branch)
