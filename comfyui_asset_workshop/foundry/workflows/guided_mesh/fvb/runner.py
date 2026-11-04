"""One owned job, sequential stages and deliberate human review boundaries."""
import asyncio
from .contracts import stages
from .journal import signature


class JobRunner:
    def __init__(self,journal,execute,fingerprint=None,interrupt=None):
        self.journal,self.execute=journal,execute
        self.fingerprint=fingerprint or (lambda job,stage:signature(dict(spec=job['spec'],stage=stage)))
        self.interrupt=interrupt
        self.active=set()
        self.lock=asyncio.Lock()

    def cancel(self,ident):
        job=self.journal.update(ident,cancelled=True,status='cancelled',awaiting_stage='')
        self.journal.event(ident,'Stopped by user. No later stage will be submitted. Completed artifacts retained.')
        if self.interrupt:
            self.interrupt(ident)
        return job

    async def advance(self,ident,continue_review=False,resume=False):
        async with self.lock:
            if self.active and ident not in self.active:
                raise ValueError('Another view-bridge job owns the heavy-work lane.')
            job=self.journal.read(ident)
            if job['cancelled'] and not resume:
                return job
            if job['status']=='awaiting_review' and not continue_review:
                return job
            if job['status']=='complete' and not resume:
                return job
            if job['status'] in ('failed','interrupted') and not resume:
                return job
            if resume:
                job=self.journal.update(ident,cancelled=False,status='ready',error='')
            self.active.add(ident)
            self.journal.update(ident,status='running',awaiting_stage='',error='')
            try:
                for stage in stages(job['spec']):
                    job=self.journal.read(ident)
                    if job['cancelled']:
                        return job
                    fingerprint=self.fingerprint(job,stage)
                    if self.journal.reusable(job,stage,fingerprint):
                        continue
                    self.journal.update(ident,current_stage=stage)
                    self.journal.event(ident,'Starting '+stage)
                    result=await self.execute(self.journal.read(ident),stage)
                    current=self.journal.read(ident)
                    # A result may complete just as cancel arrives; save it, but never continue.
                    self.journal.publish(ident,stage,result,fingerprint)
                    if current['cancelled']:
                        return self.journal.update(ident,status='cancelled',current_stage='')
                    sequence=stages(job['spec'])
                    # Old completed records may be stale. Their mere presence must never skip a review pause.
                    remaining=sequence[sequence.index(stage)+1:]
                    # Rocket is explicitly unattended. Optional review points
                    # belong to the manual wizard; actual failures still stop.
                    if job['spec']['guided'] and remaining:
                        self.journal.event(ident,'Review '+stage+'; explicit Continue is required.')
                        return self.journal.update(ident,status='awaiting_review',awaiting_stage=stage,current_stage='')
                self.journal.event(ident,'Selected pipeline completed. No optional stage was started implicitly.')
                return self.journal.update(ident,status='complete',current_stage='',awaiting_stage='')
            except (asyncio.CancelledError,InterruptedError):
                self.journal.update(ident,status='cancelled' if self.journal.read(ident)['cancelled'] else 'interrupted',current_stage='')
                raise
            except Exception as error:
                return self.journal.update(ident,status='cancelled' if self.journal.read(ident)['cancelled'] else 'failed',error=str(error),current_stage='')
            finally:
                self.active.discard(ident)
