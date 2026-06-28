from django.db.models import Q
from django.utils import timezone

from apps.sites.models import SiteSupervisor


def active_supervisor_site_links(request):
    today = timezone.localdate()
    return SiteSupervisor.objects.filter(
        company=request.company,
        supervisor=request.user,
        active_from__lte=today,
    ).filter(Q(active_until__isnull=True) | Q(active_until__gte=today))


def active_supervisor_site_ids(request):
    return active_supervisor_site_links(request).values("site_id")


def apply_active_supervisor_site_scope(queryset, *, request, site_lookup):
    if getattr(request.membership, "role", None) != "supervisor":
        return queryset
    return queryset.filter(**{f"{site_lookup}__in": active_supervisor_site_ids(request)}).distinct()


def apply_active_supervisor_worker_scope(queryset, *, request, worker_lookup):
    if getattr(request.membership, "role", None) != "supervisor":
        return queryset
    lookup_prefix = f"{worker_lookup}__" if worker_lookup else ""
    return queryset.filter(
        **{
            f"{lookup_prefix}supervisor": request.user,
            f"{lookup_prefix}default_site_id__in": active_supervisor_site_ids(request),
        }
    ).distinct()


def supervisor_has_worker_access(request, worker):
    if getattr(request.membership, "role", None) != "supervisor":
        return True
    if worker.supervisor_id != request.user.id or not worker.default_site_id:
        return False
    return active_supervisor_site_links(request).filter(site_id=worker.default_site_id).exists()
