""" Derek Moore <dmoore@mozilla.com> 11/15/2010 """

from django.shortcuts import render_to_response
from django.template import RequestContext
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist

from django.http import HttpResponse, HttpResponseRedirect
from session_csrf import anonymous_csrf
from ..models import Offender, Blacklist, ZLBVirtualServer, ZLBVirtualServerPref, ZLB, ZLBBlacklist
from ..models import ZLBVirtualServerProtection
from ..forms import ComplaintBGPBlockForm, ComplaintZLBForm
import BanHammer.blacklist.tasks as tasks

# default view for displaying all blacklists
@anonymous_csrf
def index(request, show_expired=False):
    request.session['order_by'] = request.GET.get('order_by', request.session.get('order_by', 'end_date'))
    request.session['order'] = request.GET.get('order', request.session.get('order', 'asc'))

    order_by = request.session.get('order_by', 'end_date')
    order = request.session.get('order', 'asc')

    if show_expired:
        blacklists = Blacklist.objects.filter(suggestion=False)
    else:
        blacklists = Blacklist.objects.filter(end_date__gt=datetime.now(),suggestion=False)
    
    zlb_blacklists_o = ZLBBlacklist.objects.all()
    zlb_blacklist = {}
    for z in zlb_blacklists_o:
        if z.blacklist_id not in zlb_blacklist.keys():
            zlb_blacklist[z.blacklist_id] = [z]
        else:
            zlb_blacklist[z.blacklist_id].append(z)
    for b in blacklists:
        if b.type in ['zlb_redirect', 'zlb_block']:
            b.virtual_servers = zlb_blacklist[b.id]

    if order_by == 'address':
        blacklists = sorted(list(blacklists), key=lambda blacklist: blacklist.offender.address)
    elif order_by == 'cidr':
        blacklists = sorted(list(blacklists), key=lambda blacklist: blacklist.offender.cidr)
    elif order_by == 'type':
        blacklists = sorted(list(blacklists), key=lambda blacklist: blacklist.type)
    elif order_by == 'start_date':
        blacklists = sorted(list(blacklists), key=lambda blacklist: blacklist.start_date)
    elif order_by == 'end_date':
        blacklists = sorted(list(blacklists), key=lambda blacklist: blacklist.end_date)
    elif order_by == 'reporter':
        blacklists = sorted(list(blacklists), key=lambda blacklist: blacklist.reporter)

    if order == 'desc':
        blacklists.reverse()

    data = {
        'show_expired': show_expired,
    }

    return render_to_response(
        'blacklist/index.html',
        {'blacklists': blacklists, 'data': data },
        context_instance = RequestContext(request)
    )

# view for creating new blacklists
@anonymous_csrf
def new_bgp_block(request, id=None):
    if request.method == 'POST':
        form = ComplaintBGPBlockForm(request.POST)
        if form.is_valid():

            address = form.cleaned_data['address']
            cidr = form.cleaned_data['cidr']
            type = "bgp_block"
            comment = form.cleaned_data['comment']
            bug_number = form.cleaned_data['bug_number']
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            reporter = request.META.get("REMOTE_USER")
            if not reporter:
                reporter = 'test'

            # Fetch/create the Offender and Blacklist objects.
            o, new = Offender.objects.get_or_create(
                address=address,
                cidr=cidr,
                score=0,
            )
            o.save()

            b = Blacklist(
                type=type,
                start_date=start_date,
                end_date=end_date,
                comment=comment,
                bug_number=bug_number,
                reporter=reporter,
                offender=o,
                removed=False,
            )
            b.save()
            
            _new_post(b, o, 'bgp_block')

            return HttpResponseRedirect('/blacklist')

    else:
        if id:
            offender = Offender.objects.get(id=id)
            initial = {}
            initial['target'] = '%s/%s' % (offender.address, offender.cidr)
            form = ComplaintBGPBlockForm(initial=initial)
        else:
            form = ComplaintBGPBlockForm()

    return render_to_response(
        'blacklist/new_bgp_block.html',
        {'form': form,
         'body_init': True},
        context_instance = RequestContext(request)
    )

@anonymous_csrf
def new_zlb_redirect(request, id=None):
    return new_zlb(request, 'zlb_redirect', id)

@anonymous_csrf
def new_zlb_block(request, id=None):
    return new_zlb(request, 'zlb_block', id)

@anonymous_csrf
def new_zlb(request, type, id):
    if request.method == 'POST':
        form = ComplaintZLBForm(request.POST)
        if form.is_valid():
            address = form.cleaned_data['address']
            cidr = form.cleaned_data['cidr']
            comment = form.cleaned_data['comment']
            bug_number = form.cleaned_data['bug_number']
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            reporter = request.META.get("REMOTE_USER")
            if not reporter:
                reporter = 'test'
 
            # Fetch/create the Offender and Blacklist objects.
            o, new = Offender.objects.get_or_create(
                address=address,
                cidr=cidr,
            )
            o.save()
 
            b = Blacklist(
                type=type,
                start_date=start_date,
                end_date=end_date,
                comment=comment,
                bug_number=bug_number,
                reporter=reporter,
                offender=o,
                removed=False,
            )
            b.save()
            
            for vs in form.cleaned_data['select']:
                zlb = vs.zlb
                z = ZLBBlacklist(
                    blacklist=b,
                    virtual_server_name=vs.name,
                    zlb=zlb,
                    zlb_name=zlb.name,
                )
                z.save()
 
            _new_post(b, o, type)
 
            return HttpResponseRedirect('/blacklist')
    else:
        zlbs = ZLB.objects.all()
        for zlb in zlbs:
            if zlb.updating:
                return render_to_response(
                    'zlb/updating.html',
                    {'zlb': zlb,},
                    context_instance = RequestContext(request)
                )
        if id:
            offender = Offender.objects.get(id=id)
            initial = {}
            initial['target'] = '%s/%s' % (offender.address, offender.cidr)
            form = ComplaintZLBForm(initial=initial)
        else:
            form = ComplaintZLBForm()
    zlbs_o = ZLB.objects.all()
    zlbs = {}
    for i in zlbs_o:
        zlbs[i.id] = i.name
    vs = ZLBVirtualServer.objects.all()
    prefs_o = ZLBVirtualServerPref.objects.all()
    prefs = {}
    for p in prefs_o:
        prefs[p.vs_name] = p
    return render_to_response(
        'blacklist/new_%s.html' % type,
        {'body_init': True,
         'vs': vs,
         'prefs': prefs,
         'form': form,
         'zlbs': zlbs,
         'type': type,},
        context_instance = RequestContext(request)
    )
    
def _new_post(blacklist, offender, type):
    # offender suggestion True -> False needed
    if offender.suggestion:
        offender.suggestion = False
        offender.save()
    # Celery task to send email if needed
    tasks.notification_add_blacklist.delay(blacklist.__dict__, offender.__dict__)
    # push rules to ZLBs
    if type in ['zlb_redirect', 'zlb_block']:
        if type == 'zlb_block':
            zlb_blacklist_o = ZLBBlacklist.objects.filter(blacklist=blacklist)
            for zlb_blacklist in zlb_blacklist_o:
                tasks.update_protection.delay(zlb_blacklist.zlb_id, zlb_blacklist.virtual_server_name)
        elif type == 'zlb_redirect':
            zlb_blacklist_o = ZLBBlacklist.objects.filter(blacklist=blacklist)
            for zlb_blacklist in zlb_blacklist_o:
                tasks.update_rule.delay(zlb_blacklist.zlb_id, zlb_blacklist.virtual_server_name)

def _delete_pre(request, blacklist, offender, type):
    reporter = request.META.get("REMOTE_USER")
    if not reporter:
        reporter = 'test'
    tasks.notification_delete_blacklist.delay(blacklist.__dict__, offender.__dict__, reporter)
    # delete rules on ZLBs
    if type in ['zlb_redirect', 'zlb_block']:
        if type == 'zlb_block':
            zlb_blacklist_o = ZLBBlacklist.objects.filter(blacklist=blacklist)
            for zlb_blacklist in zlb_blacklist_o:
                tasks.update_protection_delete.delay(zlb_blacklist.zlb_id, zlb_blacklist.virtual_server_name, offender)
        elif type == 'zlb_redirect':
            zlb_blacklist_o = ZLBBlacklist.objects.filter(blacklist=blacklist)
            for zlb_blacklist in zlb_blacklist_o:
                zlb_id = zlb_blacklist.zlb_id
                virtual_server_name = zlb_blacklist.virtual_server_name
                zlb_blacklist.delete()
                tasks.update_rule.delay(zlb_id, virtual_server_name)

# view for deleting blacklists
@anonymous_csrf
def delete(request):
    if request.method == 'GET':
        # Insert a confirmation dialog, at some point
        id = request.GET.get('id')

	if not id.isdigit():
            return HttpResponseRedirect('/blacklist')
        try:
            b = Blacklist.objects.get(id=id)
            _delete_pre(request, b, b.offender, b.type)
            b.delete()
        except ObjectDoesNotExist:
            return HttpResponseRedirect('/blacklist')

    return HttpResponseRedirect('/blacklist')
