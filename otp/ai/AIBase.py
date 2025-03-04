import math
import sys
import time
import gc

from direct.directnotify.DirectNotifyGlobal import *
from direct.interval.IntervalManager import ivalMgr
from direct.showbase import EventManager
from direct.showbase import ExceptionVarDump
from direct.showbase import PythonUtil
from direct.showbase.BulletinBoardGlobal import *
from direct.showbase.EventManagerGlobal import *
from direct.showbase.JobManagerGlobal import *
from direct.showbase.MessengerGlobal import *
from direct.showbase import DConfig
from direct.task import Task
from direct.task.TaskManagerGlobal import *
from otp.otpbase import BackupManager
from panda3d.core import *


class AIBase:
    notify = directNotify.newCategory('AIBase')

    def __init__(self):
        self.config = DConfig
        __builtins__['__dev__'] = self.config.ConfigVariableBool('want-dev', 0).getValue()
        logStackDump = (self.config.ConfigVariableBool('log-stack-dump', (not __dev__)).getValue() or self.config.ConfigVariableBool('ai-log-stack-dump', (not __dev__)).getValue())
        uploadStackDump = self.config.ConfigVariableBool('upload-stack-dump', 0).getValue()
        if logStackDump or uploadStackDump:
            ExceptionVarDump.install(logStackDump, uploadStackDump)
        if self.config.ConfigVariableBool('use-vfs', 1).getValue():
            vfs = VirtualFileSystem.getGlobalPtr()
        else:
            vfs = None
        self.wantTk = self.config.ConfigVariableBool('want-tk', 0).getValue()
        self.AISleep = self.config.GetFloat('ai-sleep', 0.04)
        self.AIRunningNetYield = self.config.ConfigVariableBool('ai-running-net-yield', 0).getValue()
        self.AIForceSleep = self.config.ConfigVariableBool('ai-force-sleep', 0).getValue()
        self.eventMgr = eventMgr
        self.messenger = messenger
        self.bboard = bulletinBoard
        self.taskMgr = taskMgr
        Task.TaskManager.taskTimerVerbose = self.config.ConfigVariableBool('task-timer-verbose', 0).getValue()
        Task.TaskManager.extendedExceptions = self.config.ConfigVariableBool('extended-exceptions', 0).getValue()
        self.sfxManagerList = None
        self.musicManager = None
        self.jobMgr = jobMgr
        self.hidden = NodePath('hidden')
        self.graphicsEngine = GraphicsEngine()
        globalClock = ClockObject.getGlobalClock()
        self.trueClock = TrueClock.getGlobalPtr()
        globalClock.setRealTime(self.trueClock.getShortTime())
        globalClock.setAverageFrameRateInterval(30.0)
        globalClock.tick()
        taskMgr.globalClock = globalClock
        __builtins__['ostream'] = Notify.out()
        __builtins__['globalClock'] = globalClock
        __builtins__['vfs'] = vfs
        __builtins__['hidden'] = self.hidden
        AIBase.notify.info('__dev__ == %s' % __dev__)
        #PythonUtil.recordFunctorCreationStacks()
        __builtins__['wantTestObject'] = self.config.ConfigVariableBool('want-test-object', 0).getValue()
        self.wantStats = self.config.ConfigVariableBool('want-pstats', 0).getValue()
        Task.TaskManager.pStatsTasks = self.config.ConfigVariableBool('pstats-tasks', 0).getValue()
        taskMgr.resumeFunc = PStatClient.resumeAfterPause
        defaultValue = 1
        if __dev__:
            defaultValue = 0
        wantFakeTextures = self.config.ConfigVariableBool('want-fake-textures-ai', defaultValue).getValue()
        if wantFakeTextures:
            loadPrcFileData('aibase', 'textures-header-only 1')
        self.wantPets = self.config.ConfigVariableBool('want-pets', 1).getValue()
        if self.wantPets:
            if game.name == 'toontown':
                from toontown.pets import PetConstants
                self.petMoodTimescale = self.config.GetFloat('pet-mood-timescale', 1.0)
                self.petMoodDriftPeriod = self.config.GetFloat('pet-mood-drift-period', PetConstants.MoodDriftPeriod)
                self.petThinkPeriod = self.config.GetFloat('pet-think-period', PetConstants.ThinkPeriod)
                self.petMovePeriod = self.config.GetFloat('pet-move-period', PetConstants.MovePeriod)
                self.petPosBroadcastPeriod = self.config.GetFloat('pet-pos-broadcast-period', PetConstants.PosBroadcastPeriod)
        self.wantBingo = self.config.ConfigVariableBool('want-fish-bingo', 1).getValue()
        self.wantKarts = self.config.ConfigVariableBool('wantKarts', 1).getValue()
        self.newDBRequestGen = self.config.ConfigVariableBool('new-database-request-generate', 1).getValue()
        self.waitShardDelete = self.config.ConfigVariableBool('wait-shard-delete', 1).getValue()
        self.blinkTrolley = self.config.ConfigVariableBool('blink-trolley', 0).getValue()
        self.fakeDistrictPopulations = self.config.ConfigVariableBool('fake-district-populations', 0).getValue()
        self.wantSwitchboard = self.config.ConfigVariableBool('want-switchboard', 0).getValue()
        self.wantSwitchboardHacks = self.config.ConfigVariableBool('want-switchboard-hacks', 0).getValue()
        self.GEMdemoWhisperRecipientDoid = self.config.ConfigVariableBool('gem-demo-whisper-recipient-doid', 0).getValue()
        self.sqlAvailable = self.config.ConfigVariableBool('sql-available', 1).getValue()
        self.backups = BackupManager.BackupManager(
            filepath=self.config.ConfigVariableString('backups-filepath', 'backups/').getValue(),
            extension=self.config.ConfigVariableString('backups-extension', '.json').getValue())
        self.createStats()
        self.restart()
        return

    def setupCpuAffinities(self, minChannel):
        if game.name == 'uberDog':
            affinityMask = self.config.ConfigVariableInt('uberdog-cpu-affinity-mask', -1).getValue()
        else:
            affinityMask = self.config.ConfigVariableInt('ai-cpu-affinity-mask', -1).getValue()
        if affinityMask != -1:
            TrueClock.getGlobalPtr().setCpuAffinity(affinityMask)
        else:
            autoAffinity = self.config.ConfigVariableBool('auto-single-cpu-affinity', 0).getValue()
            if game.name == 'uberDog':
                affinity = self.config.ConfigVariableInt('uberdog-cpu-affinity', -1).getValue()
                if autoAffinity and affinity == -1:
                    affinity = 2
            else:
                affinity = self.config.ConfigVariableInt('ai-cpu-affinity', -1).getValue()
                if autoAffinity and affinity == -1:
                    affinity = 1
            if affinity != -1:
                TrueClock.getGlobalPtr().setCpuAffinity(1 << affinity)
            elif autoAffinity:
                if game.name == 'uberDog':
                    channelSet = int(minChannel / 1000000)
                    channelSet -= 240
                    affinity = channelSet + 3
                    TrueClock.getGlobalPtr().setCpuAffinity(1 << affinity % 4)

    def taskManagerDoYield(self, frameStartTime, nextScheuledTaksTime):
        minFinTime = frameStartTime + self.MaxEpockSpeed
        if nextScheuledTaksTime > 0 and nextScheuledTaksTime < minFinTime:
            minFinTime = nextScheuledTaksTime
        delta = minFinTime - globalClock.getRealTime()
        while delta > 0.002:
            time.sleep(delta)
            delta = minFinTime - globalClock.getRealTime()

    def createStats(self, hostname = None, port = None):
        if not self.wantStats:
            return False
        if PStatClient.isConnected():
            PStatClient.disconnect()
        if hostname == None:
            hostname = ''
        if port == None:
            port = -1
        PStatClient.connect(hostname, port)
        return PStatClient.isConnected()

    def __sleepCycleTask(self, task):
        time.sleep(self.AISleep)
        return Task.cont

    def __resetPrevTransform(self, state):
        PandaNode.resetAllPrevTransform()
        return Task.cont

    def __ivalLoop(self, state):
        ivalMgr.step()
        return Task.cont

    def __igLoop(self, state):
        self.graphicsEngine.renderFrame()
        return Task.cont

    def shutdown(self):
        self.taskMgr.remove('ivalLoop')
        self.taskMgr.remove('igLoop')
        self.taskMgr.remove('aiSleep')
        self.eventMgr.shutdown()

    def restart(self):
        self.shutdown()
        self.taskMgr.add(self.__resetPrevTransform, 'resetPrevTransform', priority=-51)
        self.taskMgr.add(self.__ivalLoop, 'ivalLoop', priority=20)
        self.taskMgr.add(self.__igLoop, 'igLoop', priority=50)
        if self.config.ConfigVariableBool('garbage-collect-states', 1).getValue():
            self.taskMgr.add(self.__garbageCollectStates, 'garbageCollectStates', priority=46)
        if self.AISleep >= 0 and (not self.AIRunningNetYield or self.AIForceSleep):
            self.taskMgr.add(self.__sleepCycleTask, 'aiSleep', priority=55)
        self.eventMgr.restart()

    def __garbageCollectStates(self, state):
        """ This task is started only when we have
        garbage-collect-states set in the Config.prc file, in which
        case we're responsible for taking out Panda's garbage from
        time to time.  This is not to be confused with Python's
        garbage collection.  """
        
        TransformState.garbageCollect()
        RenderState.garbageCollect()
        return Task.cont

    def getRepository(self):
        return self.air

    def run(self):
        self.taskMgr.run()
