# delete
# delete and recompute the score

from django.shortcuts import render_to_response
from django.template import RequestContext

from django.http import HttpResponse, HttpResponseRedirect
from session_csrf import anonymous_csrf
from ..models import Event, Offender, AttackScoreHistory, AttackScore

@anonymous_csrf
def delete(request, id):
    event = Event.objects.get(id=id)
    offender = Offender.objects.get(address=event.attackerAddress)
    offenderscore = AttackScore.objects.get(offender=offender)
    attackscore = AttackScoreHistory.objects.get(event=event)
    
    # Substracting the attack score of the event from the offender score
    offenderscore.score -= attackscore.total_score
    offenderscore.save()
    
    event.delete()
    
    return HttpResponseRedirect('/offender/%s' % offender.id)
