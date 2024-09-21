# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from subprocess import Popen, run
import winreg
import ctypes
import sys

TITLE = 'K-LosslessCut'
VLC_INSTALLED = False


def msgbox(text, title=TITLE, style=0 | 0 | 0):
    return ctypes.windll.user32.MessageBoxW(None, text, title, style)


def check_vlc_installed():
    try:
        # VLC의 설치 경로를 저장하는 레지스트리 키
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\VideoLAN\\VLC')

        # 레지스트리 키에서 'InstallDir' 값을 가져옴
        install_dir, _ = winreg.QueryValueEx(key, 'InstallDir')

        return True
    except FileNotFoundError:
        return False


if not check_vlc_installed():
    msg = 'VLC 미디어 플레이어를 설치해야 합니다.'
    msgbox(msg)

    run(['.\\vlc-3.0.20-win64.exe'], shell=True, creationflags=0x08000000)

    if check_vlc_installed():
        VLC_INSTALLED = True
    else:
        msg = 'VLC 미디어 플레이어 설치를 취소하였습니다.\n\n프로그램을 종료합니다.'
        msgbox(msg)
        sys.exit(0)


import os
import shutil
import numpy as np
import wx
import wx.html2
import wx.dataview as dv
import wx.lib.agw.pygauge as pg
from wx.lib.dialogs import ScrolledMessageDialog
import math
import vlc
import k_losslesscut2
from k_losslesscut2 import xtimedelta, getseconds
import pickle
import psutil
import time
import re
import wave
import matplotlib
import matplotlib.pyplot as plt

matplotlib.rcParams['axes.unicode_minus'] = False
matplotlib.use('WXAgg')

VERSION = k_losslesscut2.VERSION
FFPROBE = os.getcwd() + '\\ffprobe.exe'

PREVIEW_DURATION = 3
CUTMODE = k_losslesscut2.CUTMODE
SAVE_DIR = os.path.expanduser('~') + '\\Videos\\K-LosslessCut'
DOWN_DIR = os.path.expanduser('~') + '\\Downloads'
FADE_DURATION = 0.5
FADE_EFFECT = False
WAVEFORM = True
LUFS_TARGET = -14.0
AUDIO_BITRATE = 3  # 96k
KEYFRAME_INTERVAL = 1
KEYFRAME_TIME_RANGE = 60
OPEN_ERROR = k_losslesscut2.OPEN_ERROR
FILENAME_LIMIT = k_losslesscut2.FILENAME_LIMIT


def get_rgva(rgb, alpha):
    return tuple(round(255 - alpha * (255 - v)) for v in rgb)


class PopMenu(wx.Menu):
    def __init__(self, parent, popupmenu):
        super(PopMenu, self).__init__()
        parent.just_after_popupmenu = True
        self.parent = parent
        self.popupmenu = popupmenu

        if self.popupmenu == 'left':
            self.Append(101, '파일 열기...')
            self.AppendSeparator()

        self.Append(103, '다른 이름으로 저장...')
        self.Enable(103, False)
        self.AppendSeparator()
        self.Append(201, 'LUFS 측정 / 볼륨 조정')
        self.Enable(201, False)
        self.Append(202, '볼륨 측정')
        self.Enable(202, False)
        self.AppendSeparator()
        bitrate = self.parent.audio_bitrates[self.parent.audio_bitrate]
        bps = f'({bitrate})' if bitrate else ''
        self.menu2_4 = wx.Menu()
        self.menu_audio_extract = self.menu2_4.Append(2041, f'추출{bps}')
        self.menu2_4.Append(2042, '제거')
        self.menu2_4.Append(2043, '추가')
        self.menu_audio = self.AppendSubMenu(self.menu2_4, '오디오 처리')
        self.menu_audio.Enable(False)
        # self.Append(206, '해상도 변경...')
        # self.Enable(206, False)
        self.menu2_7 = wx.Menu()
        self.menu2_7.Append(2071, '개수 지정...')
        self.menu2_7.Append(2072, '길이 지정...')
        self.menu_ntcut = self.AppendSubMenu(self.menu2_7, '분할')
        self.menu_ntcut.Enable(False)
        self.Append(213, '인코딩...')
        self.Enable(213, False)
        self.Append(214, '회전 / 뒤집기...')
        self.Enable(214, False)

        if popupmenu == 'left':
            self.Append(212, '가로형/세로형 변환...')
            self.Enable(212, False)
            self.Append(216, '종횡비 변경...')
            self.Enable(216, False)
            self.Append(211, '캡처...')
            self.Enable(211, False)

        self.AppendSeparator()
        self.Append(300, '기본앱으로 재생')
        self.Enable(300, (popupmenu == 'left' and self.parent.path != '') or
                    (popupmenu == 'right' and self.parent.path_2 != ''))
        self.AppendSeparator()
        if popupmenu == 'left':
            self.Append(217, '키프레임 타임스탬프')
            self.Enable(217, False)

        self.Append(290, '미디어 정보')
        self.Enable(290, False)

        if popupmenu == 'left':
            if self.parent.path != '':
                self.Enable(103, True)
                self.Enable(201, True)
                self.Enable(202, True)
                self.Enable(214, True)  # 메뉴: '인코딩...'
                self.menu_audio.Enable(True)  # 메뉴: '오디오 처리'
                # self.Enable(206, True)   # 메뉴: '해상도 변경...'
                self.menu_ntcut.Enable(True)  # 메뉴: '분할'
                self.Enable(213, True)  # 메뉴: '인코딩...'
                self.Enable(212, True)  # 메뉴: '가로형/세로형 변환...'
                self.Enable(216, True)  # 메뉴: '종횡비 변경...'
                self.Enable(211, True)  # 메뉴: '캡처...'
                self.Enable(217, 'key-beginning' in parent.pts and len(parent.pts['key-beginning']))
                self.Enable(290, True)  # 메뉴: '미디어 정보...'

        elif popupmenu == 'right':
            if self.parent.path_2 != '':
                not_image = self.parent.info_2[0] != '' and self.parent.info_2[3] not in ['png', 'mjpeg']
                self.Enable(103, True)
                self.Enable(201, not_image)
                self.Enable(202, not_image)
                self.Enable(214, not_image)  # 메뉴: '인코딩...'
                self.menu_audio.Enable(not_image)  # 메뉴: '오디오 처리'
                # self.Enable(206, not_image)   # 메뉴: '해상도 변경...'
                self.menu_ntcut.Enable(not_image)  # 메뉴: '분할'
                self.Enable(213, not_image)  # 메뉴: '인코딩...'
                self.Enable(290, True)  # 메뉴: '미디어 정보...'

        self.Bind(wx.EVT_MENU, self.open_external, id=300)

    def open_external(self, evt):
        if self.parent.just_after_popupmenu:
            self.parent.just_after_popupmenu = False

        if self.popupmenu == 'left':
            self.parent.playfile()
        elif self.popupmenu == 'right':
            self.parent.playfile_2()


class PopMenu2(wx.Menu):
    def __init__(self, parent, begin_end):
        super(PopMenu2, self).__init__()
        parent.just_after_popupmenu = True
        self.parent = parent

        if begin_end == '시작':
            self.Append(271, '이전 시작표시')
            self.Enable(271, len(self.parent.begin_list) > 0)
            self.Append(272, '다음 시작표시')
            self.Enable(272, len(self.parent.prev_begin_list) > 0)

            self.Bind(wx.EVT_MENU, self.parent.prevsetbegin, id=271)
            self.Bind(wx.EVT_MENU, self.parent.nextsetbegin, id=272)

        elif begin_end == '끝':
            self.Append(273, '이전 끝표시')
            self.Enable(273, len(self.parent.end_list) > 0)
            self.Append(274, '다음 끝표시')
            self.Enable(274, len(self.parent.prev_end_list) > 0)

            self.Bind(wx.EVT_MENU, self.parent.prevsetend, id=273)
            self.Bind(wx.EVT_MENU, self.parent.nextsetend, id=274)


class VideoCut(wx.Frame):
    def __init__(self, parent):
        self.parent = parent
        self.frame_width = 1218
        self.frame_height = 649
        self.cutmode = CUTMODE
        self.preview_duration = PREVIEW_DURATION
        self.fade_duration = FADE_DURATION
        self.fade_effect = FADE_EFFECT
        self.waveform = WAVEFORM
        self.lufs_target = LUFS_TARGET
        self.audio_bitrate = AUDIO_BITRATE
        self.audio_bitrates = ['', '32k', '64k', '96k', '128k', '160k', '192k', '224k', '256k', '320k']
        self.keyframe_interval = KEYFRAME_INTERVAL
        self.keyframe_interval_avg = -1
        self.keyframes_pts_range = KEYFRAME_TIME_RANGE
        self.savedir = SAVE_DIR

        self.path = ''
        self.path_2 = ''
        self.infile = ''
        self.infile2 = ''
        self.infile3 = ''
        self.file0 = ''
        self.outfile = ''
        self.duration = ''
        self.stderr = ''
        self.task = ''
        self.task2 = ''
        self.cmd = ''
        self.subtask = ''
        self.direction = ''
        self.leftright = ''
        self.begin_end = ''
        self.caption = ''
        self.taskchoice = ''
        self.obj_name = ''
        self.klosslesscut_latest_version = ''

        self.millisec_per_frame = -1
        self.lufs = -1
        self.lufs0 = -1
        self.begin = 0
        self.end = 9999999999
        self.begin2 = -1
        self.end2 = -1
        self.body_begin = -1
        self.percent = -1
        self.length = -1
        self.length_2 = -1
        self.gap = 12
        self.voladjust = 0.0
        self.count = 0
        self.segmentnum = 0
        self.segmentcount = 0
        self.segmentlen = 0
        self.totalduration = 0
        self.durationcount = 0
        self.pos = 0
        self.pos_2 = 0
        self.fps = -1
        self.t0 = 0

        self.again = False
        self.playing_in_section = False
        self.just_after_popupmenu = False
        self.just_after_slitlist = False
        self.just_after_openassource = False
        self.just_after_filedialog = False
        self.sliding = False
        self.sliding_2 = False
        self.sliderclicked = False
        self.sliderclicked_2 = False
        self.skip_set_pts_time = False
        self.popupmenu = ''
        self.fullscreen = False
        self.update_notify_klosslesscut = False

        self.size = []
        self.lufsx = []
        self.volumedetect = []
        self.split_list = []
        self.output_list = []
        self.prevfile_list = []
        self.segments = []
        self.reencode2_paths = []
        self.basic_streams = []
        self.info = []
        self.info_2 = []
        self.begin_list = []
        self.end_list = []
        self.prev_begin_list = []
        self.prev_end_list = []
        self.pids_explorer_existing = []

        self.pts = {}
        self.mediainfo = {}
        self.config = {}
        self.cutoff_list = {}
        self.orientation = {'style': '', 'fit': ''}

        self.task_label = {'lufs': 'LUFS 측정 / 볼륨 조정', 'volume': 'LUFS 측정 / 볼륨 조정', 'measurevolume': '볼륨 측정',
                           'orientation': '가로형/세로형 변환', 'extractaudio': '오디오 추출', 'remux': '리먹싱(=>mp4)',
                           'removeaudio': '오디오 제거', 'preview': '미리보기', 'cutoff': '구간 추출',
                           'music': '음악 동영상 만들기', 'music2': '음악 동영상 만들기',
                           'music3': '음악 동영상 만들기', 'addaudio': '오디오 추가', 'addaudio2': '오디오 추가',
                           'addaudio3': '오디오 추가', 'reencode': '인코딩', 'reencode2': '인코딩',
                           'saveas': '다른 이름으로 저장', 'waveform': '파형보기', 'waveform2': '파형보기',
                           'concat': '하나로 잇기', 'concat2': '하나로 잇기', 'seek-keyframe': '',
                           'ncut': '분할(개수 지정)', 'tcut': '분할(길이 지정)', 'mediainfo': '미디어 정보',
                           'capture': '캡처', 'rotate': '회전 / 뒤집기', 'ratio': '종횡비 변경'}
        self.object_alias = {}
        self.streams = set()
        self.progrdlg = None
        self.cancelled = False
        self.task_done = False
        self.worker = None
        self.worker2 = None
        self.worker3 = None
        self.worker4 = None
        self.proc = None
        self.btn_event = None
        self.rd = None
        self.rd2 = None
        self.media = None
        self.media_2 = None
        self.plt = None
        self.menu_id = None
        self.helf_frame = None

        if os.path.isfile('.\\config.pickle'):
            with open('config.pickle', 'rb') as f:
                self.config = pickle.load(f)
                if 'volume' not in self.config:
                    self.config['volume'] = 100

                if 'savedir' in self.config:
                    self.savedir = self.config['savedir']
                else:
                    self.config['savedir'] = SAVE_DIR

                if 'cutmode' in self.config:
                    self.cutmode = self.config['cutmode']
                else:
                    self.config['cutmode'] = CUTMODE

                if 'preview_duration' in self.config:
                    self.preview_duration = self.config['preview_duration']
                else:
                    self.config['preview_duration'] = PREVIEW_DURATION

                if 'fade_duration' in self.config:
                    self.fade_duration = self.config['fade_duration']
                else:
                    self.config['fade_duration'] = FADE_DURATION

                if 'fade_effect' in self.config:
                    self.fade_effect = self.config['fade_effect']
                else:
                    self.config['fade_effect'] = FADE_EFFECT

                if 'waveform' in self.config:
                    self.waveform = self.config['waveform']
                else:
                    self.config['waveform'] = WAVEFORM

                if 'lufs_target' in self.config:
                    self.lufs_target = self.config['lufs_target']
                else:
                    self.config['lufs_target'] = LUFS_TARGET

                if 'audio_bitrate' in self.config:
                    self.audio_bitrate = self.config['audio_bitrate']
                else:
                    self.config['audio_bitrate'] = AUDIO_BITRATE

                if 'keyframe_interval' in self.config:
                    self.keyframe_interval = self.config['keyframe_interval']
                else:
                    self.config['keyframe_interval'] = KEYFRAME_INTERVAL

                if 'downdir' in self.config:
                    self.downdir = self.config["downdir"]
                else:
                    self.config["downdir"] = DOWN_DIR

                l = [('resolution', '1280x720'), ('timescale', '30000'), ('pixelformat', 'yuv420p'),
                     ('videocodec', 'H.264/AVC'), ('samplerate', '44100'), ('channels', '2'), ('audiocodec', 'aac')]
                for x in l:
                    if x[0] not in self.config:
                        self.config[x[0]] = x[1]
        else:
            l = [('volume', 100), ('savedir', self.savedir), ('cutmode', self.cutmode), ('preview_duration', self.preview_duration),
                 ('fade_duration', self.fade_duration), ('fade_effect', self.fade_effect),
                 ('waveform', self.waveform), ('lufs_target', self.lufs_target), ('downdir', self.downdir),
                 ('audio_bitrate', self.audio_bitrate), ('keyframe_interval', self.keyframe_interval),
                 ('resolution', '1280x720'), ('timescale', '30000'), ('pixelformat', 'yuv420p'),
                 ('videocodec', 'H.264/AVC'), ('samplerate', '44100'), ('channels', '2'), ('audiocodec', 'aac')]

            for x in l:
                if x[0] not in self.config:
                    self.config[x[0]] = x[1]

        wx.Frame.__init__(self, None, title=TITLE,
                          size=wx.Size(self.frame_width, self.frame_height))
        self.menuBar = wx.MenuBar()
        self.menu1 = wx.Menu()
        self.menu1.Append(101, '파일 열기...')
        self.menu1.AppendSeparator()
        self.menu1.Append(103, '다른 이름으로 저장...')
        self.menu1.Enable(103, False)
        self.menu1.AppendSeparator()
        self.menu1.Append(108, '설정...')
        self.menu1.AppendSeparator()
        self.menu1.Append(104, '저장 폴더 비우기')
        self.menu1.AppendSeparator()
        self.menu1.Append(109, '닫기')
        self.menuBar.Append(self.menu1, '  파일  ')
        self.menu2 = wx.Menu()
        self.menu2.Append(201, 'LUFS 측정 / 볼륨 조정...')
        self.menu2.Enable(201, False)
        self.menu2.Append(202, '볼륨 측정...')
        self.menu2.Enable(202, False)
        self.menu2.AppendSeparator()

        bitrate = self.audio_bitrates[self.audio_bitrate]
        bps = f'({bitrate})' if bitrate else ''

        self.menu2_4 = wx.Menu()
        self.menu_audio_extract = self.menu2_4.Append(2041, f'추출{bps}...')
        self.menu2_4.Append(2042, '제거...')
        self.menu2_4.Append(2043, '추가...')
        self.menu_audio = self.menu2.AppendSubMenu(self.menu2_4, '오디오 처리')
        self.menu_audio.Enable(False)

        # self.menu2.Append(206, '해상도 변경...')
        # self.menu2.Enable(206, False)

        self.menu2_7 = wx.Menu()
        self.menu2_7.Append(2071, '개수 지정...')
        self.menu2_7.Append(2072, '길이 지정...')
        self.menu_ntcut = self.menu2.AppendSubMenu(self.menu2_7, '분할')
        self.menu_ntcut.Enable(False)

        self.menu2.Append(213, '인코딩...')
        self.menu2.Enable(213, False)

        self.menu2.Append(214, '회전 / 뒤집기...')
        self.menu2.Enable(214, False)

        self.menu2.Append(212, '가로형/세로형 변환...')
        self.menu2.Enable(212, False)

        self.menu2.Append(216, '종횡비 변경...')
        self.menu2.Enable(216, False)

        self.menu2.Append(211, '캡처...')
        self.menu2.Enable(211, False)

        self.menu2.AppendSeparator()
        self.menu2.Append(217, '키프레임 타임스탬프...')
        self.menu2.Enable(217, False)

        self.menu2.Append(290, '미디어 정보...')
        self.menu2.Enable(290, False)

        self.menu2.AppendSeparator()
        self.menu2.Append(209, '하나로 잇기...')
        self.menu2.Append(210, '음악 동영상 만들기...')

        self.menu2.Append(215, '리먹싱(=>mp4)...')

        self.menuBar.Append(self.menu2, '  도구  ')

        self.menu5 = wx.Menu()
        self.menu5.Append(501, '도움말')
        self.menu5.AppendSeparator()
        self.menu5.Append(505, '업데이트')
        self.menu5.Append(504, '정보')
        self.menuBar.Append(self.menu5, '  도움말  ')

        self.SetMenuBar(self.menuBar)

        imagefile = '.\\data\\intro.jpg'
        bmp = wx.Image(imagefile, wx.BITMAP_TYPE_ANY).ConvertToBitmap()
        self.bitmap = wx.StaticBitmap(self, -1, bmp, pos=(0, 0))
        self.pn = wx.Panel(self)
        self.pn.SetBackgroundColour('gray')

        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.player.set_hwnd(self.pn.GetHandle())
        self.player.video_set_mouse_input(False)
        self.player.video_set_key_input(False)
        self.player.audio_set_volume(self.config['volume'])

        pannel_width = 421  # height:237
        self.pn_2 = wx.Panel(self, size=(pannel_width, 237))
        self.pn_2.SetBackgroundColour('gray')
        self.instance_2 = vlc.Instance()
        self.player_2 = self.instance_2.media_player_new()
        self.player_2.set_hwnd(self.pn_2.GetHandle())
        self.player_2.video_set_mouse_input(False)
        self.player_2.video_set_key_input(False)
        self.player_2.audio_set_volume(self.config['volume'])

        self.dvlcSplitlist = dvlcSplitlist = \
            wx.dataview.DataViewListCtrl(self, size=(pannel_width + 9, -1), style=wx.BORDER_NONE)
        col_labels = [('파일명', -1)]
        for x, y in col_labels:
            dvlcSplitlist.AppendTextColumn(x, width=y)

        self.dvlcCutofflist = dvlcCutofflist = \
            wx.dataview.DataViewListCtrl(self, size=(pannel_width + 9, -1), style=wx.BORDER_NONE)
        col_labels = [('시작', 95), ('끝', 95), ('길이', 85), ('비고', -1)]
        for x, y in col_labels:
            dvlcCutofflist.AppendTextColumn(x, width=y)

        st = wx.StaticText(self, -1, '')
        self.btnClose = wx.Button(self, -1, '닫기')

        st_2 = wx.StaticText(self, -1, '')
        self.btnClose_2 = wx.Button(self, -1, '닫기')

        self.slider = wx.Slider(self, value=0, minValue=0, maxValue=100)

        self.gauge = pg.PyGauge(self, -1, size=(100, 10))
        self.gauge.SetValue([0, 0])
        self.gauge.SetBarColor(['white', 'red'])
        self.gauge.SetBackgroundColour('white')

        self.slider_2 = wx.Slider(self, value=0, minValue=0, maxValue=100)
        self.slider_2.SetMinSize((420, -1))
        self.slider_2.Disable()

        self.slider_volume = wx.Slider(self, value=100, minValue=0, maxValue=100)
        self.slider_volume.SetMinSize((90, -1))
        self.slider_volume.SetValue(self.config['volume'])
        self.slider_volume.SetToolTip(f'볼륨: {self.config["volume"]}')

        self.btnGotoBegin2_2 = wx.Button(self, -1, '|▶', size=(30, -1))  # |←
        self.btnGotoBegin2_2.SetToolTip('처음부터 재생')
        self.btnGotoBegin2_2.Disable()
        self.btnZero_2 = wx.Button(self, -1, '❚❚', size=(30, -1))
        self.btnZero_2.SetToolTip('일시 정지')
        self.btnZero_2.Disable()
        self.btnPlayEOF = wx.Button(self, -1, '▶|', size=(30, -1))
        self.btnPlayEOF.SetToolTip(f'마지막 {self.preview_duration}초 재생')
        self.btnPlayEOF.Disable()

        self.stPos_2 = wx.StaticText(self, -1, size=(65, -1), style=wx.ALIGN_RIGHT)
        self.st3_2 = wx.StaticText(self, -1, '', size=(5, -1))
        self.stDuration_2 = wx.StaticText(self, -1, size=(65, -1))

        sl = wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL)
        self.btnSetBegin = wx.Button(self, -1, '시작점 표시')
        self.btnSetBegin.SetToolTip('   현 위치에 구간 \'시작점\' 표시')
        self.btnSetEnd = wx.Button(self, -1, '끝점 표시')
        self.btnSetEnd.SetToolTip('현 위치에 구간 \'끝점\' 표시')
        self.btnGotoBegin = wx.Button(self, -1, '【←', size=(35, -1))
        self.btnGotoBegin.SetToolTip('구간 시작점으로 이동')
        self.btnGotoEnd = wx.Button(self, -1, '→】', size=(35, -1))
        self.btnGotoEnd.SetToolTip('구간 끝점으로 이동')
        self.btnGotoBegin2 = wx.Button(self, -1, '|←', size=(35, -1))
        self.btnGotoBegin2.SetToolTip('파일 맨앞으로 이동')
        self.btnPrev10 = wx.Button(self, -1, '◁10s', size=(38, -1))
        self.btnPrev10.SetToolTip('10초 후진')
        self.btnPrev1 = wx.Button(self, -1, '◁1s', size=(35, -1))
        self.btnPrev1.SetToolTip('1초 후진')
        self.btnPrevFrame = wx.Button(self, -1, '◁f', size=(35, -1))
        self.btnPrevFrame.SetToolTip('이전 프레임')
        # bmp = wx.Bitmap('src/key2.png')
        # self.btnPrevKey = wx.BitmapButton(self, -1, bitmap = bmp, size=(50, -1))
        self.btnPrevKey = wx.Button(self, -1, '◁k', size=(35, -1))
        self.btnPrevKey.SetToolTip('이전 키프레임')
        self.btnZero = wx.Button(self, -1, '❚❚', size=(50, -1))
        self.btnZeroClone = wx.Button(self, -1, '❚❚', size=(20, -1))
        self.btnStop = wx.Button(self, -1, '■', size=(25, -1))
        self.btnStop.SetToolTip('동영상 닫기')
        self.btnPlaySection = wx.Button(self, -1, '【▶】', size=(50, -1))
        font = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.btnPlaySection.SetFont(font)
        self.btnPlaySection.SetToolTip('구간 재생')
        self.btnNearFrame = wx.Button(self, -1, '⤝F⤞', size=(35, -1))
        self.btnNearFrame.SetToolTip('가까운 프레임에 맞추기')
        self.btnNearFrame.Disable()
        # self.btnNextKey = wx.BitmapButton(self, -1, bitmap = bmp, size=(50, -1))
        self.btnNextKey = wx.Button(self, -1, 'k▷', size=(35, -1))
        self.btnNextKey.SetToolTip('다음 키프레임')
        self.btnNextFrame = wx.Button(self, -1, 'f▷', size=(35, -1))
        self.btnNextFrame.SetToolTip('다음 프레임')
        self.btnNext1 = wx.Button(self, -1, '1s▷', size=(35, -1))
        self.btnNext1.SetToolTip('1초 전진')
        self.btnNext10 = wx.Button(self, -1, '10s▷', size=(37, -1))
        self.btnNext10.SetToolTip('10초 전진')

        self.stBegin = wx.StaticText(self, -1, '', size=(60, -1))
        self.stPosLabel = wx.StaticText(self, -1, '', size=(40, -1), style=wx.ALIGN_RIGHT)
        self.stPos = wx.StaticText(self, -1, '', size=(65, -1), style=wx.ALIGN_RIGHT)
        self.stPos.SetForegroundColour('blue')
        self.stPos.SetToolTip('현 위치')
        self.st3 = wx.StaticText(self, -1, '', size=(5, -1))
        self.stDuration = wx.StaticText(self, -1, '', size=(65, -1))
        self.stDuration.SetToolTip('재생 시간')
        self.stDurationLabel = wx.StaticText(self, -1, '', size=(40, -1))
        self.stEnd = wx.StaticText(self, -1, '', size=(60, -1), style=wx.ALIGN_RIGHT)

        self.cbWaveform = wx.CheckBox(self, -1, '파형 표시')
        self.cbWaveform.SetValue(self.waveform)

        self.btnCutoff = wx.Button(self, -1, '추출')
        self.btnCutoff.Disable()

        self.cbCopyStream = wx.CheckBox(self, -1, '직접 스트림 복사', size=(110, -1))
        self.cbCopyStream.SetToolTip('동영상 변환 방식 : 직접 스트림 복사')
        self.cbCopyStream.SetValue(True if self.cutmode == '직접 스트림 복사' else False)
        self.btnHelp = wx.Button(self, -1, '?', size=(22, -1))
        self.btnHelp.SetBackgroundColour((255, 255, 255))

        self.cbFade = wx.CheckBox(self, -1, f'페이드 {self.fade_duration}초')
        self.cbFade.SetValue(self.fade_effect)
        self.cbFade.Enable(False if self.cutmode == '직접 스트림 복사' else True)

        self.sl2 = wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL)

        self.stInfo = wx.StaticText(self, -1, size=(-1, 35))
        self.btnPrevSegment = wx.Button(self, -1, '❰❰', size=(30, -1))
        self.btnPrevSegment.SetToolTip('이전 동영상')
        self.btnPrevSegment.Disable()
        self.btnSplitList = wx.Button(self, -1, '분할 목록', size=(100, -1))
        self.btnNextSegment = wx.Button(self, -1, '❱❱', size=(30, -1))
        self.btnNextSegment.SetToolTip('다음 동영상')
        self.btnNextSegment.Disable()
        self.btnPrevFile = wx.Button(self, -1, '이전 파일', size=(100, -1))
        self.btnNextFile = wx.Button(self, -1, '다음 파일', size=(100, -1))
        self.btnCutoffList = wx.Button(self, -1, '추출 목록', size=(100, -1))
        self.btnOpenAsSource = wx.Button(self, -1, '왼쪽 창에서 열기', size=(100, -1))
        self.btnOpenAsSource.SetToolTip('오른쪽 창(출력 파일)의 파일을 왼쪽 창(입력 파일)에서 열기')
        self.btnOpenDir = wx.Button(self, -1, '저장폴더 열기', size=(100, -1))
        self.btnOpenDir.SetToolTip(f'출력 파일 저장 폴더({self.savedir}) 열기')
        self.btnDefaultApp = wx.Button(self, -1, '기본앱으로 재생', size=(100, -1))
        self.btnDefaultApp.SetToolTip('기본앱으로 재생')
        self.btnWaveform = wx.Button(self, -1, '파형', size=(100, -1))
        self.btnWaveform.SetToolTip('파형(waveforms) 보기')
        self.statusBar = self.CreateStatusBar(3, style=wx.BORDER_NONE)
        self.statusBar.SetStatusWidths([-1, 80, 80])
        self.SetIcon(wx.Icon("data/k-losslesscut.ico"))

        inner_4 = wx.BoxSizer(wx.HORIZONTAL)
        inner_4.Add(st, 1, wx.EXPAND)
        inner_4.Add(self.btnClose, 0)

        box = wx.StaticBox(self, -1, '분할 목록')
        self.bsizer = bsizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        bsizer.Add(dvlcSplitlist, 1, wx.EXPAND | wx.TOP | wx.BOTTOM, 5)
        bsizer.Add(inner_4, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 5)

        inner_4_2 = wx.BoxSizer(wx.HORIZONTAL)
        inner_4_2.Add(st_2, 1, wx.EXPAND | wx.ALL, 0)
        inner_4_2.Add(self.btnClose_2, 0, wx.ALL, 0)

        box = wx.StaticBox(self, -1, '추출 목록')
        self.bsizer_2 = bsizer_2 = wx.StaticBoxSizer(box, wx.VERTICAL)
        bsizer_2.Add(dvlcCutofflist, 1, wx.EXPAND | wx.TOP | wx.BOTTOM, 5)
        bsizer_2.Add(inner_4_2, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 5)

        self.inner3 = inner3 = wx.BoxSizer(wx.HORIZONTAL)
        inner3.Add(self.stBegin, 1, wx.LEFT, 10)
        inner3.Add((1, -1), 1, wx.LEFT, 5)
        inner3.Add(self.stPosLabel, 0, wx.LEFT, 5)
        inner3.Add(self.stPos, 0, wx.LEFT, 5)
        inner3.Add(self.st3, 0, wx.LEFT, 5)
        inner3.Add(self.stDuration, 0, wx.LEFT, 5)
        inner3.Add(self.stDurationLabel, 0, wx.LEFT, 5)
        inner3.Add((1, -1), 1, wx.RIGHT, 5)
        inner3.Add(self.stEnd, 1, wx.LEFT, 5)
        inner3.Add((10, -1), 0)

        self.inner_2_2_1 = inner_2_2_1 = wx.BoxSizer(wx.VERTICAL)
        inner_2_2_1_1 = wx.BoxSizer(wx.HORIZONTAL)
        inner_2_2_1_1.Add((self.gap, -1), 0)
        inner_2_2_1_1.Add(self.gauge, 1, wx.EXPAND | wx.LEFT, 1)
        inner_2_2_1_1.Add((self.gap, -1), 0)
        inner_2_2_1_2 = wx.BoxSizer(wx.HORIZONTAL)
        inner_2_2_1_2.Add(self.btnZeroClone, 1, wx.LEFT | wx.RIGHT, 10)
        inner_2_2_1.Add(inner_2_2_1_2, 0, wx.EXPAND, 0)
        inner_2_2_1.Add(self.slider, 1, wx.EXPAND)
        inner_2_2_1.Add(inner_2_2_1_1, 0, wx.EXPAND)
        inner_2_2_1.Add(inner3, 0, wx.EXPAND | wx.TOP, 10)

        self.border_left_pn = border_left_pn = wx.BoxSizer(wx.HORIZONTAL)
        border_left_pn.Add((10, -1))
        self.border_right_pn = border_right_pn = wx.BoxSizer(wx.HORIZONTAL)
        border_right_pn.Add((10, -1))

        self.inner_2_1 = inner_2_1 = wx.BoxSizer(wx.HORIZONTAL)
        inner_2_1.Add(border_left_pn)
        # inner_2_1.Add(self.browser, 1, wx.EXPAND)
        inner_2_1.Add(self.bitmap, 1, wx.EXPAND)
        inner_2_1.Add(self.pn, 1, wx.EXPAND)
        inner_2_1.Add(border_right_pn)

        self.inner_2_2 = inner_2_2 = wx.BoxSizer(wx.HORIZONTAL)
        inner_2_2.Add(inner_2_2_1, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 0)

        self.border_top_pn = border_top_pn = wx.BoxSizer(wx.VERTICAL)
        border_top_pn.Add((-1, 8))  # 21
        self.border_bottom_pn = border_bottom_pn = wx.BoxSizer(wx.VERTICAL)
        border_bottom_pn.Add((-1, 5))  # 18
        self.inner_2 = inner_2 = wx.BoxSizer(wx.VERTICAL)
        inner_2.Add(border_top_pn)
        inner_2.Add(inner_2_1, 1, wx.EXPAND)
        inner_2.Add(border_bottom_pn)
        inner_2.Add(inner_2_2, 0, wx.EXPAND)

        self.inner_3_0 = inner_3_0 = wx.BoxSizer(wx.HORIZONTAL)
        inner_3_0.Add((1, -1), 1, wx.EXPAND)
        self.inner_3_1 = inner_3_1 = wx.BoxSizer(wx.HORIZONTAL)
        inner_3_1.Add(self.slider_2, 0)

        inner_3_2 = wx.BoxSizer(wx.HORIZONTAL)
        inner_3_2.Add(self.btnPrevSegment, 0, wx.BOTTOM, 5)
        inner_3_2.Add(self.btnGotoBegin2_2, 0, wx.LEFT | wx.BOTTOM, 5)
        inner_3_2.Add(self.btnZero_2, 0, wx.LEFT | wx.BOTTOM, 5)
        inner_3_2.Add(self.btnPlayEOF, 0, wx.LEFT | wx.BOTTOM, 5)
        inner_3_2.Add(self.btnNextSegment, 0, wx.LEFT | wx.BOTTOM, 5)
        inner_3_2.Add(self.stPos_2, 0, wx.LEFT | wx.TOP, 5)
        inner_3_2.Add(self.st3_2, 0, wx.LEFT | wx.TOP, 5)
        inner_3_2.Add(self.stDuration_2, 0, wx.LEFT | wx.TOP, 5)
        inner_3_2.Add((10, -1), 0)
        inner_3_2.Add(self.slider_volume, 0, wx.LEFT, 5)

        inner_3_3 = wx.BoxSizer(wx.HORIZONTAL)
        inner_3_3.Add(self.btnWaveform, 0, wx.RIGHT, 5)
        inner_3_3.Add(self.btnOpenDir, 0, wx.RIGHT, 5)
        inner_3_3.Add(self.btnDefaultApp, 0, wx.RIGHT, 5)
        inner_3_3.Add(self.btnOpenAsSource, 0, wx.RIGHT, 5)

        inner_3_4 = wx.BoxSizer(wx.HORIZONTAL)
        inner_3_4.Add(self.btnSplitList, 0, wx.RIGHT, 5)
        inner_3_4.Add(self.btnCutoffList, 0, wx.RIGHT, 5)
        inner_3_4.Add(self.btnPrevFile, 0, wx.RIGHT, 5)
        inner_3_4.Add(self.btnNextFile, 0, wx.RIGHT, 5)

        inner_3_5 = wx.BoxSizer(wx.HORIZONTAL)
        inner_3_5.Add(self.btnPrevKey, 0, wx.RIGHT, 5)
        inner_3_5.Add(self.btnNextKey, 0, wx.RIGHT, 5)
        inner_3_5.Add(self.btnPrevFrame, 0, wx.RIGHT, 5)
        inner_3_5.Add(self.btnNearFrame, 0, wx.RIGHT, 5)
        inner_3_5.Add(self.btnNextFrame, 0, wx.RIGHT, 5)
        inner_3_5.Add(self.btnPrev1, 0, wx.RIGHT, 5)
        inner_3_5.Add(self.btnNext1, 0, wx.RIGHT, 5)
        inner_3_5.Add(self.btnPrev10, 0, wx.RIGHT, 5)
        inner_3_5.Add(self.btnNext10, 0, wx.RIGHT, 5)

        inner_3_6 = wx.BoxSizer(wx.HORIZONTAL)
        inner_3_6.Add(self.btnSetBegin, 0, wx.RIGHT, 5)
        inner_3_6.Add(self.btnSetEnd, 0, wx.RIGHT, 5)
        inner_3_6.Add(self.btnGotoBegin, 0, wx.RIGHT, 5)
        inner_3_6.Add(self.btnGotoEnd, 0, wx.RIGHT, 5)
        inner_3_6.Add(self.btnGotoBegin2, 0, wx.RIGHT, 5)
        inner_3_6.Add(self.btnZero, 0, wx.RIGHT, 5)
        inner_3_6.Add(self.btnStop, 0, wx.RIGHT, 5)
        inner_3_6.Add(self.btnPlaySection, 0, wx.RIGHT, 5)

        inner_3_7 = wx.BoxSizer(wx.HORIZONTAL)
        inner_3_7.Add(self.btnCutoff, 0, wx.TOP, 13)
        inner_3_7.Add((10, -1), 0)
        inner_3_7.Add(self.cbCopyStream, 0, wx.TOP, 17)
        inner_3_7.Add(self.btnHelp, 0, wx.TOP, 13)
        inner_3_7.Add((20, -1), 0)
        inner_3_7.Add(self.cbFade, 0, wx.TOP, 17)

        inner_3_8 = wx.BoxSizer(wx.HORIZONTAL)
        inner_3_8.Add(self.cbWaveform, 0, wx.TOP | wx.RIGHT, 4)

        box0 = wx.StaticBox(self, -1, '')
        self.bsizer0 = bsizer0 = wx.StaticBoxSizer(box0, wx.VERTICAL)
        bsizer0.Add(inner_3_0, 1, wx.EXPAND)
        bsizer0.Add(self.pn_2, 0)
        bsizer0.Add(inner_3_1, 0, wx.TOP, 5)
        bsizer0.Add(inner_3_2, 0)
        bsizer0.Add(inner_3_3, 0, wx.TOP, 5)
        bsizer0.Add(inner_3_4, 0, wx.TOP, 5)
        bsizer0.Add(sl, 0, wx.EXPAND | wx.TOP, 10)
        bsizer0.Add(inner_3_8, 0, wx.TOP, 5)
        bsizer0.Add(inner_3_5, 0, wx.TOP, 5)
        bsizer0.Add(inner_3_6, 0, wx.TOP, 5)
        bsizer0.Add(inner_3_7, 0, wx.TOP, 5)

        self.inner = inner = wx.BoxSizer(wx.HORIZONTAL)
        inner.Add(inner_2, 2, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 0)
        inner.Add(bsizer0, 1, wx.EXPAND | wx.RIGHT, 10)
        inner.Add(bsizer, 1, wx.EXPAND | wx.RIGHT | wx.TOP, 10)
        inner.Hide(bsizer)
        inner.Add(bsizer_2, 1, wx.EXPAND | wx.RIGHT | wx.TOP, 10)
        inner.Hide(bsizer_2)

        self.inner6 = inner6 = wx.BoxSizer(wx.HORIZONTAL)
        inner6.Add(self.sl2, 1, wx.ALL, 5)

        self.inner7 = inner7 = wx.BoxSizer(wx.HORIZONTAL)
        inner7.Add(self.stInfo, 1, wx.LEFT, 10)

        self.sizer1 = sizer1 = wx.BoxSizer(wx.VERTICAL)
        sizer1.Add(inner, 1, wx.EXPAND | wx.BOTTOM, 0)
        sizer1.Add(inner6, 0, wx.EXPAND | wx.BOTTOM, 5)
        sizer1.Add(inner7, 0, wx.EXPAND | wx.BOTTOM, 5)
        sizer1.Layout()
        self.SetBackgroundColour(wx.WHITE)
        self.SetSizer(sizer1)
        self.Center()
        self.setcontrols()

        self.object_alias = {self.bitmap: 'bitmap', self.pn: 'pn', self.pn_2: 'pn_2', self.slider: 'slider',
                             self.slider_2: 'slider_2', self.slider_volume: 'slider_volume',
                             self.cbCopyStream: 'cbCopyStream', self.btnHelp: 'btnHelp',
                             self.cbFade: 'cbFade', self.cbWaveform: 'cbWaveform', self.btnClose: 'btnClose',
                             self.btnClose_2: 'btnClose_2', self.btnCutoff: 'btnCutoff',
                             self.btnCutoffList: 'btnCutoffList', self.btnGotoBegin: 'btnGotoBegin',
                             self.btnGotoEnd: 'btnGotoEnd', self.btnGotoBegin2: 'btnGotoBegin2',
                             self.btnGotoBegin2_2: 'btnGotoBegin2_2', self.btnNext1: 'btnNext1',
                             self.btnNext10: 'btnNext10', self.btnNextFile: 'btnNextFile',
                             self.btnNextFrame: 'btnNextFrame', self.btnNextKey: 'btnNextKey',
                             self.btnNextSegment: 'btnNextSegment', self.btnOpenAsSource: 'btnOpenAsSource',
                             self.btnOpenDir: 'btnOpenDir', self.btnDefaultApp: 'btnDefaultApp',
                             self.btnPlayEOF: 'btnPlayEOF', self.btnPlaySection: 'btnPlaySection',
                             self.btnPrev1: 'btnPrev1', self.btnPrev10: 'btnPrev10',
                             self.btnPrevFile: 'btnPrevFile', self.btnPrevFrame: 'btnPrevFrame',
                             self.btnPrevKey: 'btnPrevKey', self.btnPrevSegment: 'btnPrevSegment',
                             self.btnSetBegin: 'btnSetBegin', self.btnSetEnd: 'btnSetEnd',
                             self.btnSplitList: 'btnSplitList', self.btnWaveform: 'btnWaveform',
                             self.btnZero: 'btnZero', self.btnZeroClone: 'btnZeroClone',
                             self.btnStop: 'btnStop', self.btnZero_2: 'btnZero_2', self.btnNearFrame: 'btnNearFrame'}

        for k in self.object_alias:
            k.Bind(wx.EVT_ENTER_WINDOW, self.onmouseenter)

        self.Bind(wx.EVT_MENU, self.onloadfile, id=101)
        self.Bind(wx.EVT_MENU, self.onsaveas, id=103)
        self.Bind(wx.EVT_MENU, self.oncleanupsavefolder, id=104)
        self.Bind(wx.EVT_MENU, self.onsetup, id=108)
        self.Bind(wx.EVT_MENU, self.onclose, id=109)
        self.Bind(wx.EVT_MENU, self.onlufs, id=201)
        self.Bind(wx.EVT_MENU, self.onmeasurevolume, id=202)
        self.Bind(wx.EVT_MENU, self.onextractaudio, id=2041)
        self.Bind(wx.EVT_MENU, self.onremoveaudio, id=2042)
        self.Bind(wx.EVT_MENU, self.onaddaudio, id=2043)
        self.Bind(wx.EVT_MENU, self.onncut, id=2071)
        self.Bind(wx.EVT_MENU, self.ontcut, id=2072)
        self.Bind(wx.EVT_MENU, self.onconcat, id=209)
        self.Bind(wx.EVT_MENU, self.onaudiopic, id=210)
        self.Bind(wx.EVT_MENU, self.oncapture, id=211)
        self.Bind(wx.EVT_MENU, self.ontransform, id=212)
        self.Bind(wx.EVT_MENU, self.onrotate, id=214)
        self.Bind(wx.EVT_MENU, self.onreencode, id=213)
        self.Bind(wx.EVT_MENU, self.onremux, id=215)
        self.Bind(wx.EVT_MENU, self.onratio, id=216)
        self.Bind(wx.EVT_MENU, self.onkeyframes_beginning, id=217)
        self.Bind(wx.EVT_MENU, self.onmediainfo, id=290)
        self.Bind(wx.EVT_MENU, self.onhelp, id=501)
        self.Bind(wx.EVT_MENU, self.onupdate_klosslesscut, id=505)
        self.Bind(wx.EVT_MENU, self.onabout, id=504)
        self.Bind(wx.EVT_MENU, self.onhelp_accel_tbl, id=5012)

        self.bitmap.Bind(wx.EVT_LEFT_UP, self.onloadfile)
        self.bitmap.Bind(wx.EVT_RIGHT_DOWN, self.onrightdown)
        self.pn.Bind(wx.EVT_LEFT_UP, self.onclick)
        self.pn.Bind(wx.EVT_RIGHT_DOWN, self.onrightdown)
        self.pn_2.Bind(wx.EVT_LEFT_UP, self.onclick_2)
        self.pn_2.Bind(wx.EVT_RIGHT_DOWN, self.onrightdown_2)

        dvlcSplitlist.Bind(wx.dataview.EVT_DATAVIEW_SELECTION_CHANGED, self.selsplitlist)
        dvlcCutofflist.Bind(wx.dataview.EVT_DATAVIEW_SELECTION_CHANGED, self.selcutofflist)
        self.btnClose.Bind(wx.EVT_BUTTON, self.onclosesplitlist)
        self.btnClose_2.Bind(wx.EVT_BUTTON, self.onclosecutofflist)
        self.slider.Bind(wx.EVT_LEFT_DOWN, self.onclickslider)
        self.slider.Bind(wx.EVT_SLIDER, self.onsliding)
        self.slider.Bind(wx.EVT_SCROLL_CHANGED, self.scrollchanged)

        self.slider_2.Bind(wx.EVT_LEFT_DOWN, self.onclickslider_2)
        self.slider_2.Bind(wx.EVT_SLIDER, self.onsliding_2)
        self.slider_2.Bind(wx.EVT_SCROLL_CHANGED, self.scrollchanged_2)

        self.slider_volume.Bind(wx.EVT_LEFT_DOWN, self.onclickslidervolume)
        self.slider_volume.Bind(wx.EVT_SLIDER, self.slidingvolume)

        self.btnHelp.Bind(wx.EVT_BUTTON, self.helpcutmode)
        self.btnSetBegin.Bind(wx.EVT_BUTTON, self.onsetbegin)
        self.btnSetBegin.Bind(wx.EVT_RIGHT_DOWN, self.onrightdown_3)
        self.btnSetEnd.Bind(wx.EVT_BUTTON, self.onsetend)
        self.btnSetEnd.Bind(wx.EVT_RIGHT_DOWN, self.onrightdown_3)
        self.btnGotoBegin.Bind(wx.EVT_BUTTON, self.ongotobegin)
        self.btnGotoEnd.Bind(wx.EVT_BUTTON, self.ongotoend)
        self.btnGotoBegin2.Bind(wx.EVT_BUTTON, self.ongotobegin2)
        self.btnPrev10.Bind(wx.EVT_BUTTON, self.onprev10secs)
        self.btnNext10.Bind(wx.EVT_BUTTON, self.onnext10secs)
        self.btnPrev1.Bind(wx.EVT_BUTTON, self.onprev1sec)
        self.btnNext1.Bind(wx.EVT_BUTTON, self.onnext1sec)
        self.btnPrevFrame.Bind(wx.EVT_BUTTON, self.onprevframe)
        self.btnNearFrame.Bind(wx.EVT_BUTTON, self.onnearframe)
        self.btnNextFrame.Bind(wx.EVT_BUTTON, self.onnextframe)
        self.btnZero.Bind(wx.EVT_BUTTON, self.onzero)
        self.btnZeroClone.Bind(wx.EVT_BUTTON, self.onzero)
        self.btnStop.Bind(wx.EVT_BUTTON, self.onstop)
        self.btnPlaySection.Bind(wx.EVT_BUTTON, self.onplaysection)
        self.btnPrevKey.Bind(wx.EVT_BUTTON, self.onprevkeyframe)
        self.btnNextKey.Bind(wx.EVT_BUTTON, self.onnextkeyframe)
        # self.btnCapture.Bind(wx.EVT_BUTTON, self.oncapture2)
        self.btnSplitList.Bind(wx.EVT_BUTTON, self.onsplitlist)
        self.btnCutoffList.Bind(wx.EVT_BUTTON, self.oncutofflist)
        self.btnPrevFile.Bind(wx.EVT_BUTTON, self.onprevfile)
        self.btnNextFile.Bind(wx.EVT_BUTTON, self.onnextfile)
        self.btnWaveform.Bind(wx.EVT_BUTTON, self.showwaveform)
        self.cbFade.Bind(wx.EVT_CHECKBOX, self.oncheckbox)
        self.cbWaveform.Bind(wx.EVT_CHECKBOX, self.oncheckbox2)
        self.btnCutoff.Bind(wx.EVT_BUTTON, self.oncutoff)
        self.cbCopyStream.Bind(wx.EVT_CHECKBOX, self.oncheckbox3)
        self.btnOpenAsSource.Bind(wx.EVT_BUTTON, self.onloadfile2)
        self.btnOpenDir.Bind(wx.EVT_BUTTON, self.opendir)
        self.btnDefaultApp.Bind(wx.EVT_BUTTON, self.playfile_2)
        self.btnPrevSegment.Bind(wx.EVT_BUTTON, self.onprevsegment)
        self.btnGotoBegin2_2.Bind(wx.EVT_BUTTON, self.ongotobegin2_2)
        self.btnZero_2.Bind(wx.EVT_BUTTON, self.onzero_2)
        self.btnPlayEOF.Bind(wx.EVT_BUTTON, self.onplayeof)
        self.btnNextSegment.Bind(wx.EVT_BUTTON, self.onnextsegment)
        self.Bind(wx.EVT_SIZE, self.onsize)
        self.Bind(wx.EVT_CLOSE, self.onwindowclose)
        self.Bind(wx.EVT_ENTER_WINDOW, self.onmouseenter)

        accel_tbl = wx.AcceleratorTable([(wx.ACCEL_NORMAL, wx.WXK_F1, 5012), (wx.ACCEL_NORMAL, 72, 5012)])
        self.SetAcceleratorTable(accel_tbl)

        self.vlc_event_manager = self.player.event_manager()
        self.vlc_event_manager.event_attach(vlc.EventType.MediaPlayerPositionChanged,
                                            self.media_position_changed)
        self.vlc_event_manager.event_attach(vlc.EventType.MediaPlayerEndReached,
                                            self.media_end_reached)

        self.vlc_event_manager_2 = self.player_2.event_manager()
        self.vlc_event_manager_2.event_attach(vlc.EventType.MediaPlayerPositionChanged,
                                              self.media_position_changed_2)
        self.vlc_event_manager_2.event_attach(vlc.EventType.MediaPlayerEndReached,
                                              self.media_end_reached_2)
        self.Connect(-1, -1, -1, self.onresult)
        if not os.path.isdir(self.savedir):
            os.makedirs(self.savedir)

        self.pn.Hide()

        if VLC_INSTALLED:
            self.task2 = 'kill-vlc'
            self.worker2 = k_losslesscut2.WorkerThread2(self)
            self.worker2.daemon = True
            self.worker2.start()

        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == 'explorer.exe':
                self.pids_explorer_existing.append(proc.info['pid'])

        wx.CallLater(1, self.check_version_latest, 'klosslesscut')

    def check_version_latest(self, arg=None):
        self.task = 'checkversion'
        self.worker4 = k_losslesscut2.WorkerThread4(self, arg)
        self.worker4.daemon = True
        self.worker4.start()

    def onmouseenter(self, evt):
        if self.object_alias is None:
            return

        if evt.GetEventObject() in self.object_alias:
            self.obj_name = self.object_alias[evt.GetEventObject()]
        else:
            self.obj_name = ''

    def onhelp_accel_tbl(self, evt):
        if self.obj_name:
            if self.obj_name in ['cbCopyStream', 'btnHelp']:
                self.helpcutmode()
            else:
                dlg = k_losslesscut2.Help(self, self.obj_name)
                dlg.ShowModal()
                dlg.Destroy()
        else:
            message = '도움말이 필요하세요?\n\n' \
                      '해당 개체가 사용 가능한 상태인가요?\n' \
                      '마우스 커서가 개체 위에 바로 놓여 있나요?\n\n' \
                      'F1 또는 H를 누르세요.'
            wx.MessageBox(message, '도움말')

    def onhelp(self, evt):
        if not self.helf_frame:
            self.helf_frame = k_losslesscut2.HelpMenu(None)

        self.helf_frame.Show()
        self.helf_frame.SetFocus()

    def onrightdown(self, evt):
        self.popupmenu = 'left'
        pmenu = PopMenu(self, self.popupmenu)
        self.PopupMenu(pmenu, evt.GetPosition())
        pmenu.Destroy()
        self.popupmenu = ''

    def onrightdown_2(self, evt):
        self.popupmenu = 'right'
        pmenu = PopMenu(self, self.popupmenu)
        x, y = self.pn_2.GetPosition() + evt.GetPosition() + (-11, -11)
        self.PopupMenu(pmenu, (x, y))
        pmenu.Destroy()
        self.popupmenu = ''

    def onrightdown_3(self, evt):
        if '시작' in evt.GetEventObject().GetLabel():
            begin_end = '시작'
            x, y = self.btnSetBegin.GetPosition() + evt.GetPosition() + (-11, -11)
        else:
            begin_end = '끝'
            x, y = self.btnSetEnd.GetPosition() + evt.GetPosition() + (-11, -11)

        pmenu = PopMenu2(self, begin_end)
        self.PopupMenu(pmenu, (x, y))
        pmenu.Destroy()

    def oncheckbox(self, evt):
        self.fade_effect = self.config['fade_effect'] = self.cbFade.GetValue()

    def oncheckbox2(self, evt):
        self.waveform = self.config['waveform'] = self.cbWaveform.GetValue()
        if self.waveform and self.stPos_2.GetLabel():
            self.showwaveform()
        else:
            plt.close()

    def oncheckbox3(self, evt):
        self.cutmode = self.config['cutmode'] = '직접 스트림 복사' if self.cbCopyStream.IsChecked() else '인코딩'
        self.cbFade.Enable(False if self.cbCopyStream.IsChecked() else True)

    def onsize(self, evt):
        self.gauge.Refresh()
        evt.Skip()

    @staticmethod
    def linapp(x1, x2, y1, y2, x):
        return int((float(x - x1) / (x2 - x1)) * (y2 - y1) + y1)

    def onsliderclick_(self, evt):
        if self.player.get_state() == vlc.State.Ended:
            self.player.set_media(self.media)
            self.play()

        if self.player.get_state() != vlc.State.Paused:
            self.player.pause()
            self.btnZero.SetLabel('▶')
            self.btnZero.SetToolTip('재생')
            self.btnZeroClone.SetLabel('▶')
            self.btnZeroClone.SetToolTip('재생')

        self.sliderclicked = True
        slider = evt.GetEventObject()
        click_min = self.gap
        click_max = slider.GetSize()[0] - self.gap
        click_position = evt.GetX()
        result_min = slider.GetMin()
        result_max = slider.GetMax()
        if click_max > click_position > click_min:
            result = self.linapp(click_min, click_max,
                                 result_min, result_max,
                                 click_position)
        elif click_position <= click_min:
            result = result_min
        else:
            result = result_max

        slider.SetValue(result)
        boolean = ('keyframes_all' in self.pts) if self.cutmode == '직접 스트림 복사' else True
        self.btnSetBegin.Enable(boolean)
        self.btnSetEnd.Enable(boolean)

        if self.playing_in_section and self.slider.GetValue() >= self.end2:
            self.playing_in_section = False
            self.setcontrols4()
            self.pause()

        self.pos = result
        self.player.set_position(self.pos / self.length)
        if self.player.get_state() != vlc.State.Ended:
            self.stPos.SetLabel(xtimedelta(self.pos))
        else:
            self.stPos.SetLabel(xtimedelta(self.length))

        self.setcontrols_start(True)
        self.setcontrols_finish(True)

        if self.player_2.get_state() == vlc.State.Playing:
            self.player_2.pause()
            self.btnZero_2.SetLabel('▶')
            self.btnZero_2.SetToolTip('재생')

        self.player.pause()
        # print('self.player.get_state()', self.player.get_state())

    def onclickslider(self, evt):
        self.onsliderclick_(evt)
        evt.Skip()

    def onclickslidervolume(self, evt):
        self.slideronclick_2(evt, '2')
        evt.Skip()

    def slideronclick_2(self, evt, arg):
        if arg == '1':
            if self.player_2.get_state() != vlc.State.Paused:
                self.player_2.pause()
                self.btnZero_2.SetLabel('▶')
                self.btnZero_2.SetToolTip('재생')

        self.sliderclicked_2 = True
        slider = evt.GetEventObject()
        click_min = self.gap
        click_max = slider.GetSize()[0] - self.gap
        click_position = evt.GetX()
        result_min = slider.GetMin()
        result_max = slider.GetMax()
        if click_max > click_position > click_min:
            result = self.linapp(click_min, click_max,
                                 result_min, result_max,
                                 click_position)
        elif click_position <= click_min:
            result = result_min
        else:
            result = result_max

        volume = result
        slider.SetValue(volume)

        if arg == '1':
            self.pos_2 = volume
            self.player_2.set_position(self.pos_2 / self.length_2)
            if self.player_2.get_state() != vlc.State.Ended:
                self.stPos_2.SetLabel(xtimedelta(self.pos_2))
            else:
                self.stPos_2.SetLabel(xtimedelta(self.length_2))

            if self.player.get_state() == vlc.State.Playing:
                self.player.pause()
                self.setcontrols2(True)
                self.btnZero.SetLabel('▶')
                self.btnZero.SetToolTip('재생')
                self.btnZeroClone.SetLabel('▶')
                self.btnZeroClone.SetToolTip('재생')

            self.player_2.pause()
            # print('self.player_2.get_state()', self.player_2.get_state())

        elif arg == '2':
            self.config['volume'] = volume
            self.slider_volume.SetToolTip(f'볼륨: {volume}')
            self.player_2.audio_set_volume(volume)

    def onclickslider_2(self, evt):
        self.slideronclick_2(evt, '1')
        evt.Skip()

    def onclosesplitlist(self, evt=None):
        # self.btnSplitList.SetFocus()
        self.inner.Hide(self.bsizer)
        self.inner.Show(self.bsizer0)

    def selsplitlist(self, evt=None):
        self.just_after_slitlist = True
        row = self.dvlcSplitlist.GetSelectedRow()
        self.btnPrevSegment.Enable(row != 0)
        self.btnNextSegment.Enable(row != len(self.split_list) - 1)
        self.addoutput()
        self.path_2 = self.split_list[row]
        self.onclosesplitlist()
        self.loadfile_2()

    def onclosecutofflist(self, evt=None):
        self.inner.Hide(self.bsizer_2)
        self.inner.Show(self.bsizer0)

    def selcutofflist(self, evt):
        self.skip_set_pts_time = True
        row = self.dvlcCutofflist.GetSelectedRow()
        self.begin2, self.end2, duration, self.cutmode = self.cutoff_list[self.path][row]
        self.stBegin.SetLabel(xtimedelta(self.begin2))
        self.stEnd.SetLabel(xtimedelta(self.end2))
        self.cbCopyStream.SetFocus()

        self.btnGotoBegin.Enable()
        self.btnGotoEnd.Enable()
        self.btnCutoff.Enable()
        self.btnCutoff.SetToolTip(f'표시된 구간({self.stBegin.GetLabel()} ~ {self.stEnd.GetLabel()}) 추출')
        if self.player.get_state() == vlc.State.Ended:
            self.player.set_media(self.media)
            if self.player.get_state() != vlc.State.Playing:
                self.player.play()

            wx.CallLater(1, self.checkplaying)
            return

        if self.playing_in_section:
            self.playing_in_section = False
            self.setcontrols4()

        self.goto(self.begin2)
        self.onset('시작')
        self.goto(self.end2)
        self.onset('끝')
        self.onplaysection()
        self.skip_set_pts_time = False
        self.dvlcCutofflist.SetFocus()

    def checkplaying(self):
        if self.player.get_state() == vlc.State.Playing:
            self.player.pause()

            self.goto(self.begin2)
            self.onset('시작')
            self.goto(self.end2)
            self.onset('끝')
            self.onplaysection()
            return

        wx.CallLater(100, self.checkplaying)

    def onclick(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False
            return

        if self.just_after_filedialog:
            self.just_after_filedialog = False
            return

        self.onzero()

    def onclick_2(self, evt):
        if self.info_2 and self.info_2[3] in ['png', 'mjpeg']:
            return

        if self.just_after_popupmenu:
            self.just_after_popupmenu = False
            return

        if self.just_after_slitlist:
            self.just_after_slitlist = False
            return

        self.onzero_2()

    def onloadfile(self, evt):
        # 이벤트 직전까지 팝업메뉴가 있었다면
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False
            # '주메뉴>파일>파일열기' 또는 '팝업메뉴>파일열기'가 아닐 때
            if evt.GetId() != 101:
                return

        wildcard = f'동영상파일 (*.mov;*.mp4;*.mkv;*.webm;*.avi;*.wmv;*.3gp;*.3g2)|' \
                   f'*.mov;*.mp4;*.mkv;*.webm;*.avi;*.wmv;*.3gp;*.3g2|모든 파일 (*.*)|*.*'
        kind = ''
        if evt is None:
            if self.task in ['capture', 'capture2']:
                kind = '동영상 '

        self.just_after_filedialog = True
        dlg = wx.FileDialog(self, message=f'{kind}파일을 선택하세요.', wildcard=wildcard,
                            style=wx.FD_OPEN | wx.FD_CHANGE_DIR)
        val = dlg.ShowModal()
        path = dlg.GetPath()
        dlg.Destroy()
        if val == wx.ID_OK:
            info = k_losslesscut2.getmediainfo(path)
            if not info:
                wx.MessageBox(f'파일을 재생할 수 없습니다.\n\n{path}\n \n파일 형식이 지원되지 않거나, '
                              f'파일 확장명이 올바르지 않거나, 파일이 손상되었을 수 있습니다.',
                              TITLE, wx.ICON_EXCLAMATION)
                return

            if info[0] == '' or info[3] in ['png', 'mjpeg']:
                if info[0] == '':
                    wx.MessageBox(f'비디오 스트림이 없는 파일입니다.\n\n{path}', TITLE, wx.ICON_EXCLAMATION)
                else:
                    wx.MessageBox(f'이미지 파일입니다.\n\n{path}', TITLE, wx.ICON_EXCLAMATION)

                return

            self.info = info
            self.loadfile(path)

    def loadfile(self, path):
        if plt.get_fignums():
            plt.close()

        if self.player.get_state() == vlc.State.Playing or self.player_2.get_state() == vlc.State.Playing:
            if self.player.get_state() == vlc.State.Playing:
                self.player.pause()

            if self.player_2.get_state() == vlc.State.Playing:
                self.player_2.pause()
                self.btnZero_2.SetLabel('▶')
                self.btnZero_2.SetToolTip('재생')

            wx.CallLater(1, self.checknotplaying, path)
        else:
            self.onreadytoloadfile(path)


    def checknotplaying(self, path):
        if self.player.get_state() != vlc.State.Playing and self.player_2.get_state() != vlc.State.Playing:
            self.onreadytoloadfile(path)
            return

        wx.CallLater(100, self.checknotplaying, path)

    def onreadytoloadfile(self, path):
        if not self.pn.IsShown():
            self.bitmap.Hide()
            self.pn.Show()

        self.inner_2_1.Layout()
        self.player.audio_set_volume(self.config['volume'])
        self.media = self.instance.media_new(path)
        self.player.set_media(self.media)
        self.path = path
        self.reset()
        # x, y = self.pn.GetSize()
        # print(x, y, x/y)

        title = self.player.get_title()
        if title == -1:
            title = path

        self.SetTitle(title)
        self.play()

    def onloadfile2(self, evt):
        if not k_losslesscut2.getmediaduration(self.path_2):
            message = f'동영상/오디오파일이 아닙니다.\n\n{self.path_2}'
            wx.MessageBox(message, '왼쪽 창에서 열기', wx.ICON_EXCLAMATION)
            return

        self.just_after_openassource = True
        self.path = self.path_2[:]
        self.info = k_losslesscut2.getmediainfo(self.path)
        self.loadfile(self.path)

    def play(self):
        self.slider.Enable()
        self.btnZero.Enable()
        self.btnZeroClone.Enable()
        self.btnStop.Enable()
        boolean = ('keyframes_all' in self.pts) if self.cutmode == '직접 스트림 복사' else True
        self.btnSetBegin.Enable(boolean)
        self.btnSetEnd.Enable(boolean)
        self.btnGotoBegin.Enable(self.stBegin.GetLabel() != '')
        self.btnGotoEnd.Enable(self.stEnd.GetLabel() != '')
        self.btnZero.SetLabel('❚❚')
        self.btnZero.SetToolTip('일시정지')
        self.btnZeroClone.SetLabel('❚❚')
        self.btnZeroClone.SetToolTip('일시정지')
        self.setcontrols2(False)
        self.btnNearFrame.Disable()
        self.btnGotoBegin2.Enable()

        if self.player.get_state() != vlc.State.Playing:
            self.player.play()

        if self.player_2.get_state() == vlc.State.Playing:
            self.player_2.pause()
            self.btnZero_2.SetLabel('▶')
            self.btnZero_2.SetToolTip('재생')

    def play_2(self):
        self.player_2.audio_set_volume(self.config['volume'])
        self.slider_2.Enable()
        self.btnGotoBegin2_2.Enable()
        self.btnZero_2.Enable()
        self.btnPlayEOF.Enable()
        self.btnZero_2.SetLabel('❚❚')
        self.btnZero_2.SetToolTip('일시정지')

        if self.player.get_state() != vlc.State.Paused:
            self.player.pause()
            self.btnZero.SetLabel('▶')
            self.btnZero.SetToolTip('재생')
            self.btnZeroClone.SetLabel('▶')
            self.btnZeroClone.SetToolTip('재생')

        if self.player_2.get_state() != vlc.State.Playing:
            self.player_2.play()

    def pause(self):
        self.btnZero.SetLabel('▶')
        self.btnZero.SetToolTip('재생')
        self.btnZeroClone.SetLabel('▶')
        self.btnZeroClone.SetToolTip('재생')
        if self.player.get_state() != vlc.State.Paused:
            self.player.pause()
            self.pos = self.player.get_time()
            self.setcontrols2(True)
            self.updatetooltip2(1)
            self.btnNearFrame.Enable(not self.btnNextFrame.GetToolTip().Tip.startswith('다음') and 'all' in self.pts and (
                        self.pos / 1000) not in self.pts)

        else:
            self.setcontrols2(True)
            self.updatetooltip()

    def pause_2(self):
        if self.player_2.get_state() != vlc.State.Paused:
            self.player_2.pause()

        pos = self.player_2.get_time()
        if pos == -1:
            return

        self.pos_2 = pos
        self.stPos_2.SetLabel(xtimedelta(self.pos_2))
        self.btnZero_2.SetLabel('▶')
        self.btnZero_2.SetToolTip('재생')
        # self.updateTooltip_2()

    def updatetooltip(self):
        s = f'({xtimedelta(self.pos)})' if self.player.get_state() == vlc.State.Paused else ''
        self.btnSetBegin.SetToolTip(f'현 위치{s}에 구간 \'시작\' 표시하기')
        self.btnSetEnd.SetToolTip(f'현 위치{s}에 구간 \'끝\' 표시하기')

    def updatetooltip2(self, arg=None):
        s = '(현위치 기준) ' if arg else ''
        self.btnNextKey.SetToolTip(f'{s}다음 키프레임')
        self.btnNextFrame.SetToolTip(f'{s}다음 프레임')
        self.btnPrevKey.SetToolTip(f'{s}이전 키프레임')
        self.btnPrevFrame.SetToolTip(f'{s}이전 프레임')
        self.btnGotoBegin2.Enable(self.pos != 0)

    def scrollchanged(self, evt):
        if self.player.get_state() == vlc.State.Playing:
            self.pause()

        self.sliding = False

    def scrollchanged_2(self, evt):
        if self.player_2.get_state() == vlc.State.Playing:
            self.pause_2()

        self.sliding_2 = False

    def onsliding(self, evt):
        if self.sliderclicked:
            self.pos = self.slider.GetValue()
            self.sliderclicked = False
            return

        if self.slider.GetValue() == self.length:
            self.pause()
            self.pos = self.length - 1
            self.player.set_position(self.pos / self.length)
            return

        self.sliding = True
        self.pos = self.slider.GetValue()
        self.player.set_position(self.pos / self.length)
        self.stPos.SetLabel(xtimedelta(self.pos))
        self.player.play()
        wx.CallLater(100, self.pausex)

    def pausex(self):
        if self.player.get_state() != vlc.State.Paused:
            self.player.pause()
            wx.CallLater(100, self.pausex)

    def onsliding_2(self, evt):
        if self.sliderclicked_2:
            self.pos_2 = self.slider.GetValue()
            self.sliderclicked_2 = False
            return

        if self.slider_2.GetValue() == self.length_2:
            self.pause_2()
            self.pos_2 = self.length_2 - 1
            self.player_2.set_position(self.pos_2 / self.length_2)
            return

        self.sliding_2 = True
        self.pos_2 = self.slider_2.GetValue()
        self.player_2.set_position(self.pos_2 / self.length_2)
        if self.player_2.get_state() != vlc.State.Ended:
            self.stPos_2.SetLabel(xtimedelta(self.pos_2))
        else:
            self.stPos_2.SetLabel(xtimedelta(self.length_2))

        self.player_2.play()
        wx.CallLater(100, self.pausex_2)

    def pausex_2(self):
        if self.player_2.get_state() != vlc.State.Paused:
            self.player_2.pause()
            wx.CallLater(100, self.pausex_2)

    def slidingvolume(self, evt):
        volume = self.slider_volume.GetValue()
        self.slider_volume.SetToolTip(f'볼륨: {volume}')

    def onvolumechanged(self, arg=None):
        volume = self.slider_volume.GetValue()
        if self.config['volume'] != volume:
            self.config['volume'] = volume
            # self.slider_volume.SetToolTip(f'볼륨: {volume}')
            if arg == 1:
                self.player.audio_set_volume(volume)
            elif arg == 2:
                self.player_2.audio_set_volume(volume)

    def init(self):
        self.length = self.player.get_length()
        self.slider.SetMax(self.length)
        self.slider.SetRange(0, self.length)
        self.stPosLabel.SetLabel('현위치')
        self.stPos.SetLabel(xtimedelta(0))
        self.st3.SetLabel('/')
        self.stDuration.SetLabel(xtimedelta(self.length))
        self.stDurationLabel.SetLabel('재생시간')

        self.fps = self.player.get_fps()
        if self.fps == 0:
            streams = k_losslesscut2.get_streams(self.path)
            video_stream = [stream for stream in streams if stream["codec_type"] == "video"]
            if video_stream:
                if 'avg_frame_rate' in video_stream[0]:
                    self.fps = float(video_stream[0]["avg_frame_rate"].split('/')[0])

                if 'start_time' in video_stream[0]:
                    start_time = float(video_stream[0]['start_time'])
                    self.mediainfo['start_time'] = start_time

                # self.seekLastFrame()

        else:
            self.millisec_per_frame = 1000 / self.fps
            # sec_per_frame = round(self.millisec_per_frame / 1000, 6)

        if 'start_time' not in self.mediainfo:
            if not self.streams:
                self.streams = k_losslesscut2.get_streams(self.path)

            video_stream = [stream for stream in self.streams if stream["codec_type"] == "video"]
            if video_stream:
                if 'start_time' in video_stream[0]:
                    start_time = float(video_stream[0]['start_time'])
                    self.mediainfo['start_time'] = start_time

    def media_position_changed(self, evt=None):
        try:
            if self.sliding:
                return

            self.pos = self.player.get_time()
            if self.length == -1:
                self.init()

            # 구간 재생
            if self.playing_in_section and self.pos >= self.end2:
                self.playing_in_section = False
                self.setcontrols4()
                self.goto(self.end2)
                return

            self.slider.SetValue(round(self.pos))
            self.stPos.SetLabel(xtimedelta(self.pos))
            boolean = ('keyframes_all' in self.pts) if self.cutmode == '직접 스트림 복사' else True
            self.btnSetBegin.Enable(boolean)
            self.btnSetEnd.Enable(boolean)
            self.onvolumechanged(1)

        except RuntimeError:
            pass

    def media_end_reached(self, evt):
        self.slider.SetValue(self.length)
        self.stPos.SetLabel(xtimedelta(self.length))
        self.btnZero.SetLabel('▶')
        self.btnZero.SetToolTip('재생')
        self.btnZeroClone.SetLabel('▶')
        self.btnZeroClone.SetToolTip('재생')
        self.slider.Disable()
        self.btnNearFrame.Disable()
        self.btnGotoBegin2.Disable()
        self.setcontrols2(False)
        if self.playing_in_section:
            self.playing_in_section = False
            self.setcontrols4()

        self.btnGotoBegin.Disable()
        self.btnGotoEnd.Disable()

    def addcutofflist(self):
        cutoff = (self.begin2, self.end2, self.end2 - self.begin2, self.cutmode)
        if cutoff not in self.cutoff_list[self.path]:
            self.cutoff_list[self.path].append(cutoff)

        self.dvlcCutofflist.DeleteAllItems()
        for cutoff in self.cutoff_list[self.path]:
            l = [xtimedelta(cutoff[0]), xtimedelta(cutoff[1]), xtimedelta(cutoff[2]), cutoff[3]]
            self.dvlcCutofflist.AppendItem(l)

        self.btnCutoffList.Enable()

    def media_position_changed_2(self, evt):
        try:
            if self.sliding_2:
                return

            if self.info_2[3] in ['png', 'mjpeg']:
                return

            self.pos_2 = self.player_2.get_time()
            if self.length_2 == -1:
                self.init_2()

            self.stPos_2.SetLabel(xtimedelta(self.pos_2))
            if self.slider_2:
                self.slider_2.SetValue(self.pos_2)

            self.onvolumechanged(2)

        except RuntimeError:
            pass

    def init_2(self):
        self.length_2 = self.player_2.get_length()
        self.slider_2.SetMax(self.length_2)
        self.slider_2.SetRange(0, self.length_2)
        self.stPos_2.SetLabel(xtimedelta(0))
        self.st3_2.SetLabel('/')
        self.stDuration_2.SetLabel(xtimedelta(self.length_2))

    def media_end_reached_2(self, evt):
        if self.info_2 and self.info_2[3] in ['png', 'mjpeg']:
            return

        if self.length_2 == -1:
            self.init_2()

        self.slider_2.SetValue(self.length_2)
        self.stPos_2.SetLabel(xtimedelta(self.length_2))
        self.btnZero_2.SetLabel('▶')
        self.btnZero_2.SetToolTip('재생')
        self.slider_2.Disable()

    def onsetup(self, evt):
        dlg = k_losslesscut2.SetupDialog(self)
        val = dlg.ShowModal()
        dlg.Destroy()
        if val == wx.ID_OK:
            if dlg.changed[0]:
                self.preview_duration = self.config['preview_duration'] = int(dlg.fs.GetValue())
                self.btnPlayEOF.SetToolTip(f'마지막 {self.preview_duration}초 재생')

            if dlg.changed[1]:
                self.fade_duration = self.config['fade_duration'] = float(dlg.fs2.GetValue())
                self.cbFade.SetLabel(f'페이드 {self.fade_duration}초')

            if dlg.changed[2]:
                self.lufs_target = self.config['lufs_target'] = float(dlg.fs3.GetValue())

            if dlg.changed[3]:
                self.audio_bitrate = self.config['audio_bitrate'] = dlg.cbBitrate.GetSelection()

            if dlg.changed[4]:
                self.keyframe_interval = self.config['keyframe_interval'] = dlg.fs4.GetValue()

            if dlg.changed[5]:
                self.savedir = self.config['savedir'] = dlg.st6.GetLabel()

            with open('config.pickle', 'wb') as f:
                pickle.dump(self.config, f)

    def helpcutmode(self, evt=None):
        dlg = k_losslesscut2.Help2(self, 1)
        dlg.ShowModal()
        dlg.Destroy()

    def opendir(self, evt):
        if self.player.get_state() == vlc.State.Playing:
            self.pause()

        if self.player_2.get_state() == vlc.State.Playing:
            self.pause_2()

        cmd = 'explorer /select,'.split() + [self.path_2]
        Popen(cmd, creationflags=0x08000000)

    def onopen_dir2(self, evt=None):
        Popen(f'explorer /select, "{self.outfile}"')

    def playfile(self):
        if self.player_2.get_state() == vlc.State.Playing:
            self.player_2.pause()

        if self.player.get_state() != vlc.State.Paused:
            self.pause()

        os.startfile(self.path)

    def playfile_2(self, evt=None):
        if self.player.get_state() == vlc.State.Playing:
            self.player.pause()

        if self.player_2.get_state() != vlc.State.Paused:
            self.pause_2()

        os.startfile(self.path_2)

    def showwaveform(self, evt=None):
        if not k_losslesscut2.isvalid(self, self.path_2):
            return

        if plt.get_fignums():
            if evt:
                plt.show()
                return
            else:
                plt.close()

        self.task = 'waveform'
        path_2 = os.path.split(self.path_2)[1][:FILENAME_LIMIT]
        if self.begin_end in ['이전', '이후']:  # 미리보기 파형이면
            message = f'{path_2}'
        else:
            message = f'{path_2} 시작부분 {self.preview_duration}초간'

        self.progrdlg = wx.GenericProgressDialog('파형', message,
                                                 maximum=100, parent=self,
                                                 style=0 | wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT)

        self.worker = k_losslesscut2.WorkerThread(self)
        self.worker.daemon = True
        self.worker.start()

    def aligntobottomright(self):
        dw, dh = wx.DisplaySize()
        w, h = self.GetSize()
        x = (dw - w)
        y = (dh - h) - 40
        self.SetPosition((x, y))

    def onupdate_klosslesscut(self, evt=None):
        if self.worker3:
            message = f'{TITLE} 다운로드 중입니다.\n\n' \
                      f'현재 버전: {VERSION}\n\n최신 버전: {self.klosslesscut_latest_version}'
            wx.MessageBox(message, TITLE, style=wx.ICON_WARNING)
            return

        if VERSION == self.klosslesscut_latest_version:
            message = f'{TITLE} 최신 버전 사용 중입니다.\n\n최신 버전: {self.klosslesscut_latest_version}'
            wx.MessageBox(message, TITLE)
            return
        else:
            self.update_notify_klosslesscut = True
            message = f'{TITLE} 최신 버전이 있습니다.  업데이트할까요?\n\n' \
                      f'현재 버전: {VERSION}\n\n최신 버전: {self.klosslesscut_latest_version}'

            with wx.MessageDialog(self, message, TITLE,
                                  style=wx.YES_NO | wx.ICON_INFORMATION) as messageDialog:
                if messageDialog.ShowModal() == wx.ID_YES:
                    if self.worker or self.worker2:
                        message = f'{self.task} 완료 후에 업데이트를 진행해주세요.\n\n '
                        wx.MessageBox(message, TITLE, style=wx.ICON_WARNING)
                        return

                    self.task = 'klosslesscut'
                    message = f'{TITLE} 설치파일 다운로드 준비 중...'
                    self.progrdlg = wx.GenericProgressDialog(f'{TITLE} 설치파일 다운로드', message,
                                                             maximum=100, parent=self,
                                                             style=0 | wx.PD_APP_MODAL | wx.PD_AUTO_HIDE |
                                                                   wx.PD_SMOOTH | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME |
                                                                   wx.PD_ESTIMATED_TIME | wx.PD_REMAINING_TIME)

                    self.worker3 = k_losslesscut2.WorkerThread3(self)
                    self.worker3.daemon = True
                    self.worker3.start()

    def onabout(self, evt):
        dlg = k_losslesscut2.Help2(self, 9)
        dlg.ShowModal()
        dlg.Destroy()

    def onresult(self, evt):
        self.SetFocus()  # VideoCut 프레임 활성화된 상태 유지
        caption = ''
        # message = ''
        if evt.data == 'finished-extract-frame':
            if self.player_2.get_state() == vlc.State.Playing:
                self.player_2.pause()

            self.loadfile_2()

        elif evt.data == 'finished-lufs':
            self.stopprogress()
            caption = 'LUFS 측정 / 볼륨 조정'
            caption2 = 'LUFS 측정'
            self.stInfo.SetLabel(f'[{caption2} 완료]\n작업 대상: {self.infile}')
            lufs = self.lufs if self.lufs != -1 else self.lufs0
            self.statusBar.SetStatusText(f'LUFS: {lufs}', 1)
            s2 = ''
            if self.lufs != -1:
                if self.voladjust:
                    s2_ = '올린 결과' if self.voladjust > 0 else ('내린 결과' if self.voladjust < 0 else '')
                    s2 += f' <= {abs(round(self.voladjust, 2))}dB {s2_}'

            # s3 = 'LUFS 측정값과 목표치 일치!' if self.lufs_target == lufs else '측정결과가 나왔습니다.'
            if self.lufs_target == lufs:
                s3 = 'LUFS 측정값과 목표치 일치!'
                wx.MessageBox(f'{s3}\n\n측정 LUFS: {lufs}{s2}\n목표 LUFS: {float(self.lufs_target)}\n\n'
                              f'{self.infile}', caption)
                return

            s3 = '측정결과가 나왔습니다.'
            file = self.infile
            # s = ''
            if self.file0:
                file = self.file0
            else:
                self.file0 = self.infile

            if self.lufs == -1:
                s = ''
                lufs = self.lufs0
                s2 = ''

            else:
                s = '다시 '
                lufs = self.lufs
                if self.voladjust:
                    s3_ = '올린 결과' if self.voladjust > 0 else ('내린 결과' if self.voladjust < 0 else '')
                    s2 = f' <= {abs(round(self.voladjust, 2))}dB {s3_}'

            volume = 0
            if self.lufs0 is not None:
                if self.lufs != -1:
                    if len(self.lufsx) < 2:
                        volume = self.lufs_target - self.lufs0 + (self.lufs_target - self.lufs)
                    else:
                        if self.lufs_target == self.lufs:
                            volume = self.lufsx[1]
                        else:
                            if (self.lufs0 < self.lufs_target <  self.lufs) or \
                                    (self.lufs0 > self.lufs_target > self.lufs):
                                volume = sum(self.lufsx) / 2
                            else:
                                if self.lufs0 < self.lufs_target and self.lufs < self.lufs_target:
                                    volume = self.lufsx[1] + abs(self.lufs_target - self.lufs)
                                elif self.lufs0 > self.lufs_target and self.lufs > self.lufs_target:
                                    volume = self.lufsx[1] - abs(self.lufs_target - self.lufs)

                else:
                    volume = self.lufs_target - self.lufs0

            self.voladjust = volume
            s4 = '올림' if volume > 0 else ('내림' if volume < 0 else '')

            with wx.MessageDialog(self, f'{s3} 볼륨을 {s}조정하겠습니까?\n\n측정 LUFS: {lufs}{s2}\n'
                                        f'목표 LUFS: {float(self.lufs_target)}\n\n'
                                        f'볼륨 조정▶ {abs(round(volume, 2))}dB {s4}\n\n{file}',
                                  caption, style=wx.YES_NO | wx.ICON_QUESTION) as messageDialog:
                if messageDialog.ShowModal() == wx.ID_YES:
                    self.onvolume()

        elif evt.data == 'cancelled-lufs':
            caption = 'LUFS 측정 / 볼륨 조정'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-measurevolume':
            self.stopprogress()
            caption = '볼륨 측정'
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            s = '\n'.join(self.volumedetect)
            message = f'{self.infile}\n \n{s}'
            wx.MessageBox(message, caption)
            self.volumedetect = []

        elif evt.data == 'cancelled-measurevolume':
            caption = '볼륨 측정'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-volume':
            self.stopprogress()
            if len(self.lufsx) == 2:
                del self.lufsx[0]

            self.lufsx.append(self.voladjust)
            plus = '올렸음' if self.voladjust > 0 else ('내렸음' if self.voladjust < 0 else '')
            caption = 'LUFS 측정 / 볼륨 조정'
            caption2 = '볼륨 조정'
            self.statusBar.SetStatusText(f'({self.statusBar.GetStatusText(1)})', 1)
            self.statusBar.SetStatusText(f'볼륨: {abs(round(self.voladjust, 2))} {plus}', 2)
            self.stInfo.SetLabel(f'[{caption2} 완료]\n작업 대상: {self.infile}')
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            s = '올렸음' if self.voladjust > 0 else ('내렸음' if self.voladjust < 0 else '')
            with wx.MessageDialog(self, f'볼륨을 조정하였습니다. LUFS를 측정하겠습니까?\n\n'
                                        f'{abs(round(self.voladjust, 2))}dB {s}\n\n{self.path_2}',
                                  caption, style=wx.YES_NO | wx.ICON_QUESTION) as messageDialog:

                if messageDialog.ShowModal() == wx.ID_YES:
                    self.infile = self.path_2
                    if self.lufs != -1:
                        self.lufs = -1

                    self.onlufs()

        elif evt.data == 'cancelled-volume':
            caption = 'LUFS 측정 / 볼륨 조정'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-saveas':
            self.stopprogress()
            caption = '다른 이름으로 저장'
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()

            wx.MessageBox(f'{caption} 완료\n\n{self.infile}\n\n=>\n\n{self.outfile}', caption,
                          wx.ICON_INFORMATION)

        elif evt.data == 'cancelled-saveas':
            caption = '다른 이름으로 저장'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-orientation':
            self.stopprogress()
            caption = '가로형/세로형 변환'
            self.stInfo.SetLabel(f'[{caption} 완료]\n{self.subtask}, {self.direction}\n작업 대상: {self.infile}')
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            wx.MessageBox(f'{caption} 완료\n\n{self.subtask}, {self.direction}\n\n{self.infile}\n\n=>\n\n'
                          f'{self.outfile}', caption,
                          wx.ICON_INFORMATION)

        elif evt.data == 'finished-ratio':
            self.stopprogress()
            caption = '종횡비 변경'
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            wx.MessageBox(f'{caption} 완료\n\n{self.infile}\n\n=>\n\n'
                          f'{self.outfile}', f'{caption} => {self.size[0]}:{self.size[1]}',
                          wx.ICON_INFORMATION)

        elif evt.data == 'cancelled-ratio':
            caption = '종횡비 변경'
            self.killtask(f'{caption}을 취소하였습니다.', f'{caption} => {self.size[0]}:{self.size[1]}')

        elif evt.data == 'finished-rotate':
            self.stopprogress()
            choices = ['회전(90° 반시계 방향)', '회전(90° 시계 방향)', '회전(180°)', '뒤집기(좌우)', '뒤집기(상하)',
                       '회전(90° 반시계 방향) + 뒤집기(상하)', '회전(90° 시계 방향) + 뒤집기(상하)']
            caption = f'회전 / 뒤집기 => {choices[int(self.subtask)]}'
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            wx.MessageBox(f'{caption} 완료\n\n{self.infile}\n\n=>\n\n{self.outfile}',
                          caption)

        elif evt.data == 'cancelled-orientation':
            caption = '가로형/세로형 변환'
            self.killtask(f'{caption}을 취소하였습니다.', f'{caption}')

        elif evt.data == 'cancelled-rotate':
            choices = ['회전(90° 반시계 방향)', '회전(90° 시계 방향)', '회전(180°)', '뒤집기(좌우)', '뒤집기(상하)',
                       '회전(90° 반시계 방향) + 뒤집기(상하)', '회전(90° 시계 방향) + 뒤집기(상하)']
            caption = f'회전 / 뒤집기 => {choices[int(self.subtask)]}'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-extractaudio':
            self.stopprogress()
            caption = '오디오 추출'
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            wx.MessageBox(f'{caption} 완료\n\n{self.infile}\n\n=>\n\n'
                          f'{self.outfile}', caption)

        elif evt.data == 'cancelled-extractaudio':
            caption = '오디오 추출'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-removeaudio':
            self.stopprogress()
            caption = '오디오 제거'
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            wx.MessageBox(f'{caption} 완료\n\n{self.infile}\n\n=>\n\n'
                          f'{self.outfile}', caption)

        elif evt.data == 'cancelled-removeaudio':
            caption = '오디오 제거'
            self.killtask(f'{caption}를 취소하였습니다.', caption)

        elif evt.data in ['finished-preview', 'finished-cutoff']:
            self.stopprogress()
            if self.task == 'preview':
                caption = f'현 위치 {self.begin_end} {self.preview_duration}초 미리보기'
                self.dvlcCutofflist.UnselectAll()

            elif self.task == 'cutoff':
                caption = '구간 추출'
                self.addcutofflist()

            if not self.file0:
                self.file0 = self.path_2[:]

            self.loadfile_2()
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.path}')
            if self.waveform:
                info_2 = k_losslesscut2.getmediainfo(self.path_2)
                # 오디오 스트림이 있으면
                if info_2[4]:
                    wx.CallLater(500, self.showwaveform)
            else:
                self.setcontrols3()

        elif evt.data in ['cancelled-preview', 'cancelled-cutoff']:
            if self.task == 'preview':
                caption = '미리보기'

            elif self.task == 'cutoff':
                caption = '구간 추출'

            self.killtask(f'{caption}를 취소하였습니다.', caption)
            self.setcontrols3()

        elif evt.data == 'finished-remux':
            self.stopprogress()
            caption = '리먹싱(=>mp4)'
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            wx.MessageBox(f'{caption} 완료\n\n{self.infile}\n\n=>\n\n{self.outfile}', caption,
                          wx.ICON_INFORMATION)

        elif evt.data == 'cancelled-remux':
            caption = 'Remux'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-waveform':
            self.stopprogress()
            if self.begin_end in ['이전', '이후']:
                self.stInfo.SetLabel(f'[파형 완료]\n작업 대상: {self.path_2}')

                idx = self.path_2.rfind('.')
                infile = self.path_2[:idx] + '.wav'
                wav = wave.open(infile, 'r')
                raw = wav.readframes(-1)
                raw = np.frombuffer(raw, dtype=np.int16)
                samplerate = wav.getframerate()
                if wav.getnchannels() == 2:
                    print('스테레오 파일은 지원하지 않습니다. 모노 파일을 사용하세요.')
                    return

                t = np.linspace(0, len(raw) / samplerate, num=len(raw))
                plt.figure('파형')
                plt.rc('font', family='Malgun Gothic')
                plt.title(f'{self.stPos.GetLabel()} {self.begin_end} {self.preview_duration}초')
                x, y = self.GetPosition()
                x_, y_ = self.pn.GetPosition()
                mngr = plt.get_current_fig_manager()
                mngr.window.SetPosition((x + x_, y + 51 + y_))
                w, h = self.pn.GetSize()
                mngr.window.SetSize(w + 15, h + 7)
                plt.plot(t, raw)
                plt.xlabel('시간(초)', labelpad=0, loc='right')
                plt.ylabel('진폭', labelpad=0, loc='top')
                plt.tick_params(direction='in')
                plt.grid()
                plt.show()
                self.setcontrols3()
            else:
                self.task = 'waveform2'
                message = f'{os.path.split(self.path_2)[1][:FILENAME_LIMIT]} 끝부분 {self.preview_duration}초간'
                self.progrdlg = wx.GenericProgressDialog('파형보기', message,
                                                         maximum=100, parent=self,
                                                         style=0 | wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT)

                self.worker = k_losslesscut2.WorkerThread(self)
                self.worker.daemon = True
                self.worker.start()

        elif evt.data in ['cancelled-waveform', 'cancelled-waveform2']:
            caption = '파형'
            self.killtask(f'{caption}를 취소하였습니다.', caption)
            self.setcontrols3()

        elif evt.data == 'finished-waveform2':
            self.stopprogress()
            self.stInfo.SetLabel(f'[파형 완료]\n작업 대상: {self.path_2}')

            idx = self.path_2.rfind('.')
            infile = self.path_2[:idx] + '.wav'
            wav = wave.open(infile, 'r')
            raw = wav.readframes(-1)
            raw = np.frombuffer(raw, dtype=np.int16)
            samplerate = wav.getframerate()
            if wav.getnchannels() == 2:
                print('스테레오 파일은 지원하지 않습니다. 모노 파일을 사용하세요.')
                return

            t = np.linspace(0, len(raw) / samplerate, num=len(raw))
            plt.figure('파형')
            plt.rc('font', family='Malgun Gothic')
            plt.subplot(2, 1, 1)
            x, y = self.GetPosition()
            mngr = plt.get_current_fig_manager()
            mngr.window.SetPosition((x + 10, y + 60))
            if self.stBegin.GetLabel():
                plt.title(f'처음 {self.preview_duration}초({self.stBegin.GetLabel()} 이후 {self.preview_duration}초)')
            else:
                plt.title(f'처음 {self.preview_duration}초')

            plt.plot(t, raw)
            # plt.xlabel('time(sec)')
            plt.ylabel('진폭', labelpad=0, loc='top')
            plt.tick_params(direction='in')
            plt.grid()

            infile2 = self.path_2[:idx] + '2.wav'
            wav2 = wave.open(infile2, 'r')
            raw2 = wav2.readframes(-1)
            raw2 = np.frombuffer(raw2, dtype=np.int16)

            t2 = np.linspace(0, len(raw2) / samplerate, num=len(raw2))
            plt.subplot(2, 1, 2)
            if self.stEnd.GetLabel():
                plt.title(f'마지막 {self.preview_duration}초({self.stEnd.GetLabel()} 이전 {self.preview_duration}초)')
            else:
                plt.title(f'마지막 {self.preview_duration}초')

            plt.plot(t2, raw2)
            plt.xlabel('시간(초)', labelpad=0, loc='right')
            plt.tick_params(direction='in')
            plt.subplots_adjust(left=0.12, bottom=0.1, right=0.9, top=0.9, wspace=0.4, hspace=0.4)
            plt.grid()
            plt.show()
            self.setcontrols3()

        elif evt.data in ['finished-ncut', 'finished-tcut']:
            self.stopprogress()
            if self.segmentcount == self.segmentnum:
                self.split_list = []
                self.dvlcSplitlist.DeleteAllItems()
                for segment in self.segments:
                    self.split_list.append(segment)
                    self.dvlcSplitlist.AppendItem([os.path.split(segment)[1]])
                segments = ",\n\n".join(self.segments)
                if self.task == 'ncut':
                    caption = '분할(개수 지정)'

                else:
                    caption = '분할(길이 지정)'

                self.addoutput()
                self.path_2 = self.segments[0]
                self.btnPrevSegment.Disable()
                self.btnNextSegment.Disable()
                self.loadfile_2()
                self.clearntcutfiles()
                self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
                if self.task == 'ncut':
                    segmentnum = f'분할 개수: {self.segmentnum}'
                    wx.MessageBox(f'{caption} 완료\n\n'
                                  f'{segmentnum}\n\n{self.infile}\n\n=>\n\n{segments}',
                                  caption)
                else:
                    segmentlen = f'분할 길이: {int(self.segmentlen / 1000)}초, {xtimedelta(self.segmentlen)}'
                    wx.MessageBox(f'{caption} 완료\n\n'
                                  f'{segmentlen}\n\n{self.infile}\n\n=>\n\n{segments}',
                                  caption)

            if self.segmentcount < self.segmentnum:
                self.duration = ''
                self.begin += self.segmentlen
                self.segmentcount += 1
                if self.task == 'ncut':
                    self.onncut()

                else:
                    self.ontcut()

        elif evt.data == 'cancelled-ncut':
            caption = '분할(개수 지정)'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'cancelled-tcut':
            caption = '분할(길이 지정)'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-concat':
            self.stopprogress()
            self.totalduration += getseconds(self.duration)
            if self.segmentcount == len(self.segments):
                self.task = 'concat2'
                k_losslesscut2.doit(self)

            else:
                self.segmentcount += 1
                self.onconcat()

        elif evt.data == 'finished-concat2':
            self.stopprogress()
            if self.segments:
                pass
            else:
                print('>>> no-segments')
                basename = os.path.basename(self.path)
                name, ext = os.path.splitext(basename)
                begin_ = xtimedelta(self.begin).replace(":", ".")
                end_ = xtimedelta(self.end).replace(":", ".")
                basename_ = f'[cut]{name} {begin_}-{end_}{ext}'
                outfile = rf'{self.savedir}\{basename_}'
                if os.path.isfile(outfile):
                    os.remove(outfile)

                os.rename(self.outfile, outfile)
                self.outfile = outfile

            self.addoutput()
            self.path_2 = self.outfile
            self.loadfile_2()
            if self.segments:
                caption = '하나로 잇기'
                segments = ""
                for i in range(len(self.segments)):
                    segments += f'파일 #{i + 1}: {self.segments[i]}'
                    if i < len(self.segments) - 1:
                        segments += '\n\n'

                self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
                message = f'{caption} 완료\n\n{segments}\n\n=>\n\n{self.outfile}'
                wx.MessageBox(message, caption)
            else:
                caption = '구간 추출'
                self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.path}')

        elif evt.data in ['cancelled-concat', 'cancelled-concat2']:
            caption = '하나로 잇기'
            self.killtask(f'{caption}를 취소하였습니다.', caption)

        elif evt.data == 'finished-music3':
            self.stopprogress()
            caption = '음악 동영상 만들기'
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            wx.MessageBox(f'{caption} 완료\n\n오디오: {self.infile}\n\n'
                          f'이미지: {self.infile2}\n\n=>\n\n{self.outfile}', caption,
                          wx.ICON_INFORMATION)

        elif evt.data == 'cancelled-music3':
            self.streams = []
            caption = '음악 동영상 만들기'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-addaudio':
            self.stopprogress()
            if 'video' in self.streams:
                self.streams = []
                self.onaddaudio2()

            else:
                wx.MessageBox(f'비디오 스트림이 없는 파일입니다.\n{self.path_2}', '오디오 추가', wx.ICON_EXCLAMATION)
                self.streams = []
                self.onaddaudio()

        elif evt.data == 'finished-addaudio2':
            self.stopprogress()
            if 'audio' in self.streams:
                self.streams = []
                self.onaddaudio3()

            else:
                wx.MessageBox(f'오디오가 없는 파일입니다.\n{self.infile2}', '오디오 추가', wx.ICON_EXCLAMATION)
                self.streams = []
                self.onaddaudio2()

        elif evt.data == 'finished-addaudio3':
            self.stopprogress()
            caption = '오디오 추가'
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            wx.MessageBox(f'{caption} 완료\n\n{self.infile}, \n{self.infile2}\n\n=>\n\n{self.outfile}',
                          caption)

        elif evt.data in ['cancelled-addaudio', 'cancelled-addaudio2', 'cancelled-addaudio3']:
            self.streams = []
            caption = '오디오 추가'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-reencode':
            self.stopprogress()
            caption = '인코딩'
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')
            wx.MessageBox(f'{caption} 완료\n\n{self.infile}\n\n=>\n\n'
                          f'{self.outfile}', caption)
            with wx.MessageDialog(self, f'미디어 정보를 원합니까?\n\n{self.outfile}', caption,
                                  style=wx.YES_NO | wx.ICON_QUESTION) as messageDialog:
                if messageDialog.ShowModal() == wx.ID_YES:
                    self.infile = self.outfile
                    self.onmediainfo(None)

        elif evt.data == 'cancelled-reencode':
            caption = '인코딩'
            self.killtask(f'{caption}을 취소하였습니다.', caption)

        elif evt.data == 'finished-reencode2':
            self.stopprogress()
            caption = '인코딩'
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.infile}')

            self.rd2.items.append(self.outfile)
            self.rd2.lc.Append(self.outfile)
            self.rd2.lc.Check(len(self.rd2.items) - 1)
            self.rd2.OnCheck()

            if len(self.reencode2_paths) > 1:
                self.infile = self.reencode2_paths.pop(0)
                k_losslesscut2.doit(self, caption)
            else:
                self.rd2.need_reencode2 = False
                self.rd2.btnOk.Enable()
                checked_items = [(self.rd2.lc.GetString(x), x) for x in range(len(self.rd2.lc.GetItems()))
                                 if self.rd2.lc.IsChecked(x)]
                reencode2_paths = [x for x in self.reencode2_paths[-1][0] if x != self.reencode2_paths[-1][1]]
                for item in checked_items:
                    file, idx = item
                    if file in reencode2_paths:
                        self.rd2.lc.Check(idx, False)

                num_checked = len(self.rd2.lc.GetCheckedItems())
                self.rd2.tc.SetValue(f"{num_checked}")

                message = ''
                for i in range(len(reencode2_paths)):
                    infile = reencode2_paths[i]
                    outfile = rf'{self.savedir}\[reencode2]{os.path.basename(infile)}'
                    message += f'파일 #{i + 1}: {infile}\n=> {outfile}'
                    if i < len(reencode2_paths) - 1:
                        message += ',\n\n'

                wx.MessageBox(f'{caption} 완료\n\n{message}', caption)
                self.task = 'concat'
                with wx.MessageDialog(self, '\'하나로 잇기\'를 실행할까요?\n\n ', caption,
                                      style=wx.YES_NO | wx.ICON_QUESTION) as messageDialog:
                    if messageDialog.ShowModal() == wx.ID_YES:
                        k_losslesscut2.concat_(self)
                        k_losslesscut2.doit(self)

        elif evt.data == 'cancelled-reencode2':
            self.reencode2_paths = []
            self.killtask(f'{caption}를 취소하였습니다.', '인코딩')
            self.task = 'concat'

        elif evt.data in ['finished-capture', 'finished-capture2']:
            caption = '캡처'
            self.addoutput()
            self.path_2 = self.outfile[:]
            self.loadfile_2()
            self.stInfo.SetLabel(f'[{caption} 완료]\n작업 대상: {self.path}')

        elif evt.data in ['cancelled-capture', 'cancelled-capture2']:
            caption = '캡처'
            self.killtask(f'{caption}를 취소하였습니다.', caption)

        elif evt.data == 'finished-checkversion':
            self.worker4 = None
            self.onupdate_klosslesscut()
            pass

        elif evt.data == 'cancelled-checkversion':
            self.worker4 = None
            pass

        elif evt.data == 'finished-klosslesscut':
            self.progrdlg.Destroy()
            self.worker3 = None
            caption = 'K-LosslessCut 설치파일 다운로드'
            self.stInfo.SetLabel(f'[{caption} 완료]\n{self.outfile}')
            message = f'업데이트를 진행하려면 일단 프로그램을 닫은 후 설치파일을 실행해야 합니다. 계속할까요?\n\n' \
                      f'설치파일: {self.outfile}'

            with wx.MessageDialog(self, message, f'{TITLE} 업데이트',
                                  style=wx.YES_NO | wx.ICON_QUESTION) as messageDialog:
                if messageDialog.ShowModal() == wx.ID_YES:
                    self.Close()
                    self.onopen_dir2()

        elif evt.data == 'cancelled-klosslesscut':
            self.progrdlg.Destroy()
            self.worker3 = None
            caption = 'K-LosslessCut 설치파일 다운로드'
            self.stInfo.SetLabel(f'[{caption} 취소]')
            wx.MessageBox(f'{caption}를 취소하였습니다.\n\n ', caption)
            os.remove(self.outfile)

    def togglebtncutoff(self):
        if self.btnCutoff.IsEnabled():
            self.btnCutoff.SetBackgroundColour('#333')
            self.btnCutoff.SetForegroundColour('white')
            self.btnCutoff.SetWindowStyleFlag(wx.NO_BORDER)
            self.btnCutoff.SetToolTip(f'지정된 구간({self.stBegin.GetLabel()} ~ {self.stEnd.GetLabel()}) 추출')
        else:
            self.btnCutoff.SetBackgroundColour('silver')
            self.btnCutoff.SetForegroundColour('black')
            self.btnCutoff.SetWindowStyleFlag(wx.SIMPLE_BORDER)

        self.btnPlaySection.Enable(self.btnCutoff.IsEnabled())

    def stopprogress(self):
        self.progrdlg.Update(100)
        self.progrdlg.Destroy()
        if self.proc:
            Popen(f'TASKKILL /F /PID {self.proc.pid} /T', creationflags=0x08000000)

        if self.btn_event:
            if self.btn_event.GetLabel() == '추출':
                if self.waveform:
                    if self.task == 'waveform2':
                        self.btnCutoff.Enable()
                        self.togglebtncutoff()
                        self.btn_event = None
                else:
                    self.btnCutoff.Enable()
                    self.togglebtncutoff()
                    self.btn_event = None

    def killtask(self, message, caption):
        if self.proc:
            if self.progrdlg:
                self.progrdlg.Destroy()

            # creationflags=0x08000000: CREATE_NO_WINDOW
            Popen(f'TASKKILL /F /PID {self.proc.pid} /T', creationflags=0x08000000)
            wx.CallLater(1000, self.clearfiles)

        if self.btn_event:
            if self.btn_event.GetLabel() == '추출':
                self.btnCutoff.Enable()
                self.togglebtncutoff()
                self.btn_event = None

        self.stInfo.SetLabel(f'[{caption} 취소]\n작업 대상: {self.path}')
        wx.MessageBox(message, caption)

    def clearfiles(self):
        if self.task in ['ncut', 'tcut']:
            basename = os.path.basename(self.infile)
            name, ext = os.path.splitext(basename)
            i = 0
            while 1:
                i += 1
                basename_ = f'[{self.task}]{name} ({i}){ext}'
                outfile = rf'{self.savedir}\{basename_}'
                if os.path.isfile(outfile):
                    os.remove(outfile)
                else:
                    break
        else:
            if os.path.isfile(self.path_2):
                os.remove(self.path_2)

    def clearntcutfiles(self):
        basename = os.path.basename(self.infile)
        name, ext = os.path.splitext(basename)
        name_ = f'[{self.task}]{name}'
        name_ = re.sub('\[', '\[', name_)
        name_ = re.sub('\(', '\(', name_)
        name_ = re.sub('\)', '\)', name_)
        name_ = re.sub('{', '{', name_)
        name_ = re.sub('}', '}', name_)
        regex = f"{name_} \(\d+\){ext}"
        p = re.compile(regex)
        filenames = os.listdir(self.savedir)
        for filename in filenames:
            m = p.match(filename)
            if m:
                filepath = f'{self.savedir}\\{filename}'
                m = re.search(f'\((\d+)\){ext}$', filepath)
                if m:
                    if int(m.group(1)) > self.segmentnum:
                        os.remove(filepath)

    def oncleanupsavefolder(self, evt):
        filenames = os.listdir(self.savedir)
        files_num = len(filenames)
        if files_num == 0:
            message = f'저장 폴더가 비어 있습니다.\n\n '
            wx.MessageBox(message, TITLE, wx.ICON_INFORMATION)
            return

        with wx.MessageDialog(self, f'한번 삭제한 파일은 복구할 수 없습니다. \'저장 폴더 비우기\'를 실행할까요?\n\n삭제 예정 파일: {files_num}개', TITLE,
                              style=wx.YES_NO | wx.ICON_WARNING) as messageDialog:
            if messageDialog.ShowModal() != wx.ID_YES:
                return

        for filename in os.listdir(self.savedir):
            path = os.path.join(self.savedir, filename)
            if path == self.path:
                message = f'왼쪽 창의 동영상을 닫습니다.\n\n{path}'
                wx.MessageBox(message, TITLE, wx.ICON_EXCLAMATION)
                self.player.stop()
                self.reset()

            elif path == self.path_2:
                message = f'오른쪽 창의 동영상을 닫습니다.\n\n{path}'
                wx.MessageBox(message, TITLE, wx.ICON_EXCLAMATION)
                self.player_2.stop()
                self.reset_2()
                self.setcontrols_2()

            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except RuntimeError as e:
                message = f'삭제 실패\n\n{e}'
                wx.MessageBox(message, TITLE, wx.ICON_EXCLAMATION)

        wx.CallLater(1000, self.cleanupresult, files_num)

    def cleanupresult(self, files_num):
        filenames2 = os.listdir(self.savedir)
        message = f'저장 폴더의 파일을 삭제하였습니다.\n\n삭제 성공: {files_num - len(filenames2)}개\n\n' \
                  f'삭제 실패: {len(filenames2)}개'
        wx.MessageBox(message, TITLE, wx.ICON_INFORMATION)

    def loadfile_2(self):
        if not os.path.isfile(self.path_2):
            wx.MessageBox(f'지정된 파일을 찾을 수 없습니다.\n\n{self.path_2}', TITLE, wx.ICON_EXCLAMATION)
            return

        if self.player_2.get_state() == vlc.State.Playing:
            # self.player_2.stop()
            self.player_2.pause()
            wx.CallLater(1, self.checknotplaying_2)
        else:
            self.onreadytoloadfile_2()

    def checknotplaying_2(self):
        if self.player_2.get_state() != vlc.State.Playing:
            self.onreadytoloadfile_2()
            return

        wx.CallLater(100, self.checknotplaying_2)

    def onreadytoloadfile_2(self):
        self.player_2.audio_set_volume(self.config['volume'])
        self.media_2 = self.instance_2.media_new(self.path_2)
        self.player_2.set_media(self.media_2)

        self.info_2 = k_losslesscut2.getmediainfo(self.path_2)
        self.reset_2()
        basename = os.path.basename(self.path_2)
        if self.info_2 and self.info_2[3] in ['png', 'mjpeg']:
            self.player_2.play()
            time.sleep(0.001)
            self.player_2.pause()
            self.setcontrols5()
            self.pn_2.SetToolTip(f'{basename}')
        else:
            self.play_2()
            if self.info_2 and self.info_2[0] == '':
                self.pn_2.SetToolTip(f'{basename}')
            else:
                self.pn_2.SetToolTip(f'{basename}')

        self.statusBar.SetStatusText(basename, 0)

        if self.task == 'preview':
            self.statusBar.SetStatusText('', 1)
        else:
            file_size = os.path.getsize(self.path_2)
            if file_size >= 1024 * 1024 * 10:
                text = f'{round(file_size / 1024 / 1024, 1)}MB'
            elif file_size >= 1024 * 1024:
                text = f'{round(file_size / 1024 / 1024, 2)}MB'
            elif file_size >= 1024:
                text = f'{round(file_size / 1024)}KB'
            else:
                text = f'{file_size}바이트'

            self.statusBar.SetStatusText(text, 1)

        self.onclosesplitlist()
        self.onclosecutofflist()

        self.btnOpenDir.Enable()
        self.btnDefaultApp.Enable()
        # self.btnHelp2.Enable()
        # self.btnHelp2.SetBackgroundColour((255, 255, 255))
        self.btnNextSegment.Enable(len(self.split_list) > 0 and
                                   self.dvlcSplitlist.GetSelectedRow() != len(self.split_list) - 1)
        self.btnSplitList.Enable(len(self.split_list) > 0)
        self.btnCutoffList.Enable(self.path in self.cutoff_list)
        self.btnPrevFile.Enable(len(self.output_list) > 0)
        self.btnNextFile.Enable(len(self.prevfile_list) > 0)
        self.btnOpenAsSource.Enable(self.info_2[0] != '' and self.info_2[3] not in ['png', 'mjpeg'])
        self.btnWaveform.Enable(self.info_2[3] not in ['png', 'mjpeg'])
        wx.CallLater(1000, self.clear_just_after_slitlist)

    def clear_just_after_slitlist(self):
        self.just_after_slitlist = False

    def onprev10secs(self, evt):
        pos = self.mediainfo['start_time'] * 1000 \
            if self.pos - 10000 < self.mediainfo['start_time'] * 1000 else self.pos - 10000
        self.moveposition(pos)

    def onprev1sec(self, evt):
        pos = self.mediainfo['start_time'] * 1000 \
            if self.pos - 1000 < self.mediainfo['start_time'] * 1000 else self.pos - 1000
        self.moveposition(pos)

    def onprevframe(self, evt):
        try:
            pts = [x for x in self.pts['all'] if x < (self.pos / 1000 - 0.5 * self.millisec_per_frame / 1000)][-1]
            idx = self.pts['all'].index(pts)
            pts_ = self.pts['all2'][idx]
            self.player.set_position(pts_ * 1000 / self.length)
        except IndexError:
            self.player.set_position(0)

        self.media_position_changed()
        self.updatetooltip2()
        self.setcontrols2(True)

    def onprevkeyframe(self, evt):
        # pts = 0
        try:
            pts = [x for x in self.pts['keyframes_all'] if x < self.pos / 1000][-1]
            self.player.set_position(pts * 1000 / self.length)
        except IndexError:
            self.player.set_position(0)

        self.media_position_changed()
        self.updatetooltip2()
        self.setcontrols2(True)

    def onzero(self, evt=None):
        self.pos = self.player.get_time()
        self.player.audio_set_volume(self.config['volume'])
        if self.player.get_state() == vlc.State.Playing:
            self.pause()

        elif self.player.get_state() == vlc.State.Paused:
            self.play()

        elif self.player.get_state() == vlc.State.Ended:
            self.player.set_media(self.media)
            self.play()

    def onzero_2(self, evt=None):
        self.player_2.audio_set_volume(self.config['volume'])
        if self.player_2.get_state() == vlc.State.Playing:
            self.pause_2()

        elif self.player_2.get_state() == vlc.State.Paused:
            self.play_2()

        elif self.player_2.get_state() == vlc.State.Ended:
            self.ongotobegin2_2()

    def onstop(self, evt):
        self.player_2.stop()
        self.player.stop()
        self.pn.Hide()
        self.bitmap.Show()
        self.reset()
        self.reset_2()

    def onplayeof(self, evt):
        self.checkplayer_2()
        self.pos_2 = self.length_2 - self.preview_duration * 1000
        self.setplayer_2()

    def onplaysection(self, evt=None):
        if self.playing_in_section:
            self.playing_in_section = False
            self.setcontrols4()
        else:
            self.playing_in_section = True
            self.setcontrols4()
            if self.end2 == -1:
                self.end2 = self.length

            self.goto(self.begin2)
            self.play()

    def setcontrols4(self):
        if self.playing_in_section:
            self.btnPlaySection.SetBackgroundColour(wx.RED)
            self.btnPlaySection.SetForegroundColour('white')
            self.btnPlaySection.SetWindowStyleFlag(wx.NO_BORDER)
        else:
            self.btnPlaySection.SetBackgroundColour('silver')
            self.btnPlaySection.SetForegroundColour('black')
            self.btnPlaySection.SetWindowStyleFlag(wx.SIMPLE_BORDER)

    def onnextkeyframe(self, evt):
        try:
            pts = [x for x in self.pts['keyframes_all'] if x > self.pos / 1000][0]
            self.player.set_position(pts * 1000 / self.length)
        except ValueError:
            self.player.set_position((self.length - 1) / self.length)

        self.media_position_changed()
        self.updatetooltip2()
        self.setcontrols2(True)

    def onnextframe(self, evt=None):
        try:
            pts = [x for x in self.pts['all'] if x > (self.pos / 1000 + 0.5 * self.millisec_per_frame / 1000)][0]
            idx = self.pts['all'].index(pts)
            pts_ = self.pts['all2'][idx]
            self.player.set_position(pts_ * 1000 / self.length)
        except IndexError as e:
            print(e)
            self.player.set_position((self.length - 1) / self.length)

        self.media_position_changed()
        self.updatetooltip2()
        self.setcontrols2(True)

    def onnext1sec(self, evt):
        pos = self.length if self.pos + 1000 > self.length else self.pos + 1000
        self.moveposition(pos)

    def onnext10secs(self, evt):
        pos = self.length if self.pos + 10000 > self.length else self.pos + 10000
        self.moveposition(pos)

    def moveposition(self, pos):
        if 'all' in self.pts:
            self.findnearestframe2(self.pts['all'], pos)
        elif 'current' in self.pts and \
                (max(self.pts['current']) >= pos/1000 >= min(self.pts['current'])):
            self.findnearestframe2(self.pts['current'], pos)
        else:
            self.pos = pos
            self.findnearestframe()

    def findnearestframe(self):
        self.task2 = 'find-nearest-frame'
        self.worker2 = k_losslesscut2.WorkerThread2(self)
        self.worker2.daemon = True
        self.worker2.start()

    def findnearestframe2(self, pts, pos):
        nearest_pts = min(pts, key=lambda x: abs(pos / 1000 - x))
        self.player.set_position(nearest_pts * 1000 / self.length)
        self.media_position_changed()
        self.updatetooltip2()
        self.setcontrols2(True)

    def onnearframe(self, evt):
        nearest_pts = self.pos / 1000
        try:
            pts = [x for x in self.pts['all'] if x > self.pos / 1000][0]
            idx = self.pts['all'].index(pts)
            pts_ = self.pts['all2'][idx]
            pts2 = [x for x in self.pts['all'] if x < self.pos / 1000][-1]
            idx = self.pts['all'].index(pts2)
            pts2_ = self.pts['all2'][idx]
            if pts_ - self.pos / 1000 < self.pos / 1000 - pts2_:
                nearest_pts = pts_
            else:
                nearest_pts = pts2_
        except IndexError:
            pass

        self.player.set_position(nearest_pts * 1000 / self.length)
        self.media_position_changed()
        self.updatetooltip2()
        self.setcontrols2(True)

    def do(self, plus, arg):
        pos = self.pos
        if arg == 'PREVIOUS':
            if pos + plus < 0:
                pos = 0
            else:
                pos += plus

        if arg == 'NEXT':
            if pos + plus >= self.length:
                pos = self.length
                self.player.set_position(1)
                self.player.play()
                self.setcontrols2(False)

            else:
                pos += plus

        self.btnGotoBegin.SetLabel('【')
        self.btnGotoEnd.SetLabel('】')
        self.player.set_position(pos / self.length)
        self.pos = self.player.get_time()
        self.stPos.SetLabel(xtimedelta(self.pos))
        if arg != 'zero':
            self.slider.SetValue(int(self.pos))

        if self.pos == 0:
            self.setcontrols_start(False)

        elif self.pos == self.length:
            self.setcontrols_finish(False)

        else:
            self.setcontrols_start(True)
            self.setcontrols_finish(True)

        self.updatetooltip()

    def ongotobegin(self, evt=None):
        self.goto(self.begin2)
        self.pos = self.begin2
        self.btnGotoBegin.Disable()
        self.btnGotoEnd.Enable(self.stEnd.GetLabel() != '')
        self.btnGotoBegin2.Enable(self.pos != 0)

    def ongotoend(self, evt):
        if self.end2 == -1:
            self.goto(self.length)
        else:
            self.goto(self.end2)

        self.pos = self.end2
        self.btnGotoBegin.Enable(self.stBegin.GetLabel() != '')
        self.btnGotoEnd.Disable()

    def ongotobegin2(self, evt):
        self.pause()
        self.player.set_position(0)
        self.stPos.SetLabel(xtimedelta(0))
        self.slider.SetValue(0)
        self.pos = 0
        if self.player.get_state() == vlc.State.Paused:
            self.btnGotoBegin2.Disable()

        self.setcontrols2(True)

    def checkplayer_2(self):
        if self.player.get_state() == vlc.State.Playing:
            self.pause()

        if self.player_2.get_state() == vlc.State.Ended:
            self.player_2.set_media(self.media_2)
            self.play_2()
        elif self.player_2.get_state() != vlc.State.Playing:
            self.player_2.play()

    def setplayer_2(self):
        self.slider_2.SetValue(self.pos_2)
        self.player_2.set_position(self.pos_2 / self.length_2)
        self.stPos_2.SetLabel(xtimedelta(self.pos_2))

    def ongotobegin2_2(self, evt=None):
        self.checkplayer_2()
        self.pos_2 = 0
        self.setplayer_2()

    def goto(self, pos):
        if self.player.get_state() == vlc.State.Playing:
            self.pause()

        self.player.set_position(pos / self.length)
        self.stPos.SetLabel(xtimedelta(pos))
        self.slider.SetValue(round(pos))

    def goto2(self):
        if self.player.get_state() == vlc.State.Playing:
            self.pause()

        self.player.set_position(0)
        self.stPos.SetLabel(xtimedelta(0))
        self.slider.SetValue(0)
        self.pos = 0

    def goto_2(self, pos):
        if self.player_2.get_state() == vlc.State.Playing:
            self.pause_2()

        self.player_2.set_position(pos / self.length_2)
        self.stPos_2.SetLabel(xtimedelta(pos))
        self.slider_2.SetValue(round(pos))

    def prevsetbegin(self, evt):
        self.prev_begin_list.append(self.stBegin.GetLabel())
        self.begin_end = '시작'
        begin = self.begin_list.pop()
        self.begin2 = getseconds(begin) * 1000
        self.onset_begin_end()
        self.slider.SetValue(round(self.begin2))

    def nextsetbegin(self, evt):
        self.begin_list.append(self.stBegin.GetLabel())
        self.begin_end = '시작'
        begin = self.prev_begin_list.pop()
        self.begin2 = getseconds(begin) * 1000
        self.onset_begin_end()
        self.slider.SetValue(round(self.begin2))

    def prevsetend(self, evt):
        self.prev_end_list.append(self.stEnd.GetLabel())
        self.begin_end = '끝'
        end = self.end_list.pop()
        self.end2 = getseconds(end) * 1000
        self.onset_begin_end()
        self.slider.SetValue(round(self.end2))

    def nextsetend(self, evt):
        self.end_list.append(self.stEnd.GetLabel())
        self.begin_end = '끝'
        end = self.prev_end_list.pop()
        self.end2 = getseconds(end) * 1000
        self.onset_begin_end()
        self.slider.SetValue(round(self.end2))

    def onsetbegin(self, evt):
        label = self.stBegin.GetLabel()
        ### if getseconds(label)*1000 == self.pos:
        ###    return

        if label != '':
            self.begin_list.append(label)

        self.disable5buttons()
        self.onset('시작')

    def onsetend(self, evt):
        label = self.stEnd.GetLabel()
        ### if getseconds(label)*1000 == self.pos:
        ###    return

        if label != '':
            self.end_list.append(label)

        self.disable5buttons()
        self.onset('끝')

    def onset(self, arg):
        if self.player.get_state() != vlc.State.Paused:
            self.pause()
            self.stPos.SetLabel(xtimedelta(self.pos))

        self.setcolor(arg)
        self.begin_end = arg
        if arg == '시작':
            self.stBegin.SetLabel('')
        elif arg == '끝':
            self.stEnd.SetLabel('')

        if self.skip_set_pts_time:
            self.onset_begin_end()

        else:
            if arg == '시작' and self.cutmode == '직접 스트림 복사':
                self.pos = self.getframe('key', self.pos / 1000) * 1000

            self.stPos.SetLabel(xtimedelta(self.pos))
            if arg == '시작':
                self.begin2 = self.pos
            else:
                self.end2 = self.pos

            self.onset_begin_end()

    def onset_begin_end(self):
        if self.begin2 < 0:
            self.begin2 = 0

        if self.begin_end == '시작':
            if self.cutmode == '직접 스트림 복사':
                self.ongotobegin()
                # self.setcontrols2(True)

            self.player.set_position(self.begin2 / self.length)
            self.stBegin.SetLabel(xtimedelta(self.begin2))
            begin = self.begin2 * 100 / self.length
            if begin > 99.9:
                begin = 99.9

            if self.stEnd.GetLabel():
                if self.stBegin.GetLabel() == self.stEnd.GetLabel():
                    self.gauge.SetValue([0, 0])
                else:
                    end = getseconds(self.stEnd.GetLabel()) * 100000 / self.length
                    if end > 100:
                        end = 100

                    if self.begin2 < getseconds(self.stEnd.GetLabel()) * 1000:
                        self.gauge.SetBarColor(['white', 'red'])
                    else:
                        self.gauge.SetBarColor([wx.Colour(get_rgva((255, 0, 0), 0.3)), 'white'])
                        self.btnCutoff.Disable()

                    self.gauge.SetValue([begin, end])

            else:
                self.stEnd.SetForegroundColour('red')
                self.stEnd.SetLabel(self.stDuration.GetLabel())
                self.gauge.SetValue([begin, 100])

        elif self.begin_end == '끝':
            self.player.set_position(self.end2 / self.length)
            self.stPos.SetLabel(xtimedelta(self.end2))
            self.stEnd.SetLabel(xtimedelta(self.end2))
            end = self.end2 * 100 / self.length
            if self.stBegin.GetLabel():
                if self.stBegin.GetLabel() == self.stEnd.GetLabel():
                    self.gauge.SetValue([0, 0])
                else:
                    begin = getseconds(self.stBegin.GetLabel()) * 100000 / self.length
                    if self.end2 > getseconds(self.stBegin.GetLabel()) * 1000:
                        self.gauge.SetBarColor(['white', 'red'])
                    else:
                        self.gauge.SetBarColor([wx.Colour(get_rgva((255, 0, 0), 0.3)), 'white'])
                        self.btnCutoff.Disable()

                    if end - begin < 0.08658359296772744:
                        end = begin + 0.08658359296772744

                    self.gauge.SetValue([begin, end])
            else:
                self.stBegin.SetForegroundColour('red')
                self.stBegin.SetLabel(xtimedelta(0))
                self.gauge.SetValue([0, end])

        self.gauge.Refresh()
        if self.begin_end == '시작':
            self.onpreview('이후')
        elif self.begin_end == '끝':
            self.onpreview('이전')

    def setcolor(self, arg):
        if arg == '시작':
            pos = self.stBegin.GetLabel()
            self.stBegin.SetLabel('')
            self.stBegin.SetForegroundColour('red')
            self.stBegin.SetLabel(pos)
        elif arg == '끝':
            pos = self.stEnd.GetLabel()
            self.stEnd.SetLabel('')
            self.stEnd.SetForegroundColour('red')
            self.stEnd.SetLabel(pos)

    def onprevsegment(self, evt):
        row = self.dvlcSplitlist.GetSelectedRow()
        row_prev = row - 1
        self.dvlcSplitlist.SelectRow(row_prev)
        self.selsplitlist()

    def onnextsegment(self, evt):
        row = self.dvlcSplitlist.GetSelectedRow()
        row_next = 0
        if row == -1:
            row_next = 1
        elif row < self.dvlcSplitlist.ItemCount - 1:
            row_next = row + 1

        self.dvlcSplitlist.SelectRow(row_next)
        self.selsplitlist()

    def onsplitlist(self, evt):
        self.dvlcSplitlist.SetFocus()
        if self.dvlcSplitlist.GetSelectedRow() == -1:
            if os.path.basename(self.path_2)[:6] in ['[ncut]', '[tcut]']:
                self.dvlcSplitlist.SelectRow(0)

        self.inner.Hide(self.bsizer0)
        self.inner.Show(self.bsizer)
        self.Layout()

    def oncutofflist(self, evt):
        self.dvlcCutofflist.SetFocus()
        self.dvlcCutofflist.UnselectAll()
        num_rows = len(self.cutoff_list[self.path])
        for row in range(num_rows):
            if self.stBegin.GetLabel() == self.dvlcCutofflist.GetValue(row, 0) and \
                    self.stEnd.GetLabel() == self.dvlcCutofflist.GetValue(row, 1) and \
                    self.dvlcCutofflist.GetValue(row, 3) == '직접 스트림 복사':
                self.dvlcCutofflist.SelectRow(row)
                break

        self.inner.Hide(self.bsizer0)
        self.inner.Show(self.bsizer_2)
        self.Layout()

    def onprevfile(self, evt):
        self.prevfile_list.append(self.path_2)
        self.path_2 = self.output_list.pop()
        self.loadfile_2()
        self.stInfo.SetLabel(f'[이전 파일]\n{self.path_2}')
        if len(self.output_list) == 0:
            self.btnPrevFile.Disable()

    def onnextfile(self, evt):
        self.output_list.append(self.path_2)
        self.path_2 = self.prevfile_list.pop()
        self.loadfile_2()
        self.stInfo.SetLabel(f'[다음 파일]\n{self.path_2}')
        if len(self.prevfile_list) == 0:
            self.btnNextFile.Disable()

    def addoutput(self):
        if self.path_2 != '':
            self.output_list.append(self.path_2)

    def oncutoff(self, evt):
        caption = '구간 추출'
        # message = ''

        if self.end2 == -1:
            self.end2 = self.length

        begin = self.begin2 / 1000
        end = self.end2 / 1000

        if begin >= end:
            message = f'구간의 시작/끝이 맞게 표시되었는지 확인해주세요:\n\n' \
                      f'시작 : {self.stBegin.GetLabel()}\n   끝 : {self.stEnd.GetLabel()}'
            caption = '구간 추출'
            wx.MessageBox(message, caption, wx.ICON_EXCLAMATION)
            return

        if self.player.get_state() != vlc.State.Paused:
            self.pause()

        if self.player_2.get_state() != vlc.State.Paused:
            self.pause_2()

        self.begin_end = ''
        basename = os.path.basename(self.path)
        name, ext = os.path.splitext(basename)
        begin_ = xtimedelta(self.begin2).replace(":", ".")
        end_ = xtimedelta(self.end2).replace(":", ".")
        basename_ = f'[cut]{name} {begin_}-{end_}{ext}'
        # basename_ = f'[cut]{name} {begin_}-{end_} {self.cutmode.replace(" ", "")}{ext}'

        if self.path not in self.cutoff_list:
            self.cutoff_list[self.path] = []

        self.addoutput()
        self.path_2 = rf'{self.savedir}\{basename_}'

        self.progrdlg = wx.GenericProgressDialog(caption, f'{caption} 시작...',
                                                 maximum=100, parent=self,
                                                 style=0 | wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_SMOOTH
                                                       | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_ESTIMATED_TIME
                                                       | wx.PD_REMAINING_TIME)

        self.btn_event = self.btnCutoff
        self.disable5buttons()

        self.duration = ''
        self.task = 'cutoff'
        self.begin = begin
        self.end = end
        self.worker = k_losslesscut2.WorkerThread(self)
        self.worker.daemon = True
        self.worker.start()
        self.setcontrols5()

    def disable5buttons(self):
        self.btnSetBegin.Disable()
        self.btnSetEnd.Disable()
        self.btnCutoff.Disable()
        self.btnGotoBegin.Disable()
        self.btnGotoEnd.Disable()

    def onremux(self, evt):
        wildcard = '동영상파일 (*.mov;*.mkv;*.webm;*.avi;*.wmv;*.3gp;*.3g2)|' \
                   '*.mov;*.mkv;*.webm;*.avi;*.wmv;*.3gp;*.3g2|모든 파일 (*.*)|*.*'
        dlg = wx.FileDialog(self, message='파일을 선택하세요.', wildcard=wildcard,
                            style=wx.FD_OPEN | wx.FD_CHANGE_DIR)
        val = dlg.ShowModal()
        path = dlg.GetPath()
        dlg.Destroy()
        if val == wx.ID_OK:
            info = k_losslesscut2.getmediainfo(path)
            if not info:
                wx.MessageBox(f'파일을 재생할 수 없습니다.\n\n{path}\n \n파일 형식이 지원되지 않거나, '
                              '파일 확장명이 올바르지 않거나, 파일이 손상되었을 수 있습니다.',
                              TITLE, wx.ICON_EXCLAMATION)
                return

            if info[0] == '' or info[3] in ['png', 'mjpeg']:
                if info[0] == '':
                    wx.MessageBox(f'비디오 스트림이 없는 파일입니다.\n\n{path}',
                                  TITLE, wx.ICON_EXCLAMATION)
                else:
                    wx.MessageBox(f'이미지 파일입니다.\n\n{path}',
                                  TITLE, wx.ICON_EXCLAMATION)

                return

            self.infile = path
            self.info = info
            self.task = 'remux'
            k_losslesscut2.doit(self)

        else:
            return

    def onkeyframes_beginning(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        pts = self.pts['key-beginning']
        pts_ = '\n'.join([str(x) for x in pts])
        pts_range = f'전체 {self.length / 1000}' if self.length / 1000 < self.keyframes_pts_range \
            else f'시작부 {self.keyframes_pts_range}'
        message = f'{self.path}\n\n탐색 범위: {pts_range}초\n \n{pts_}'
        if len(pts) > 1:
            message += f'\n\n키프레임 간격(최빈값): {self.keyframe_interval_avg}초'

        caption = '키프레임 타임스탬프'
        ScrolledMessageDialog(self, message, caption, size=(500, 600)).ShowModal()

    def onmediainfo(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'mediainfo'
        k_losslesscut2.doit(self, event=evt)

    def getframesall(self):
        self.task2 = 'pts-all'
        self.worker2 = k_losslesscut2.WorkerThread2(self)
        self.worker2.daemon = True
        self.worker2.start()

    def onlufs(self, evt=None):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'lufs'
        if evt:
            self.voladjust = 0

        k_losslesscut2.doit(self, event=evt)

    def onmeasurevolume(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'measurevolume'
        k_losslesscut2.doit(self, event=evt)

    def onconcat(self, evt=None):
        self.task = 'concat'
        k_losslesscut2.doit(self, event=evt)

    def onaudiopic(self, evt=None):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'music'
        k_losslesscut2.doit(self)

    def onaudiopic2(self):
        self.task = 'music2'
        k_losslesscut2.doit(self)

    def onaudiopic3(self):
        self.task = 'music3'
        k_losslesscut2.doit(self)

    def onaddaudio(self, evt=None):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'addaudio'
        k_losslesscut2.doit(self, event=evt)

    def onaddaudio2(self):
        self.task = 'addaudio2'
        k_losslesscut2.doit(self)

    def onaddaudio3(self):
        self.task = 'addaudio3'
        k_losslesscut2.doit(self)

    def onvolume(self, evt=None):
        self.task = 'volume'
        k_losslesscut2.doit(self, event=evt)

    def onpreview(self, arg):
        if self.length == -1:
            return

        if self.player.get_state() != vlc.State.Paused:
            self.pause()

        if self.path_2:
            if self.player_2.get_state() != vlc.State.Paused:
                self.pause_2()

        start = -1
        stop = self.length / 1000 + 1
        caption = f'현 위치 {arg} {self.preview_duration}초 미리보기'
        if arg == '이후':
            try:
                if self.player.get_state() == vlc.State.Ended:
                    self.pos = self.length

                start = self.pos / 1000
            except ValueError:
                start = 0

            if self.length / 1000 - start < self.preview_duration:
                if self.pos == self.length:
                    message = f'현 위치({xtimedelta(self.pos)})는 파일의 끝입니다.'
                    wx.MessageBox(message, caption, wx.ICON_EXCLAMATION)
                    return

                message = f'현 위치({xtimedelta(start * 1000)})에서 추출할 수 있는 길이는 ' \
                          f'{round(self.length / 1000 - start, 3)}초입니다.'

                if self.length / 1000 - start == 0:
                    wx.MessageBox(message, caption, wx.ICON_EXCLAMATION)
                    return

            stop = start + self.preview_duration
            if stop > self.length / 1000:
                stop = self.length / 1000

        elif arg == '이전':
            try:
                stop = self.pos / 1000
            except ValueError:
                stop = self.length / 1000

            if stop < self.preview_duration:
                if stop == 0:
                    message = f'현 위치({xtimedelta(self.pos)})는 파일의 처음입니다.'
                    wx.MessageBox(message, caption, wx.ICON_EXCLAMATION)
                    return

            start = stop - self.preview_duration
            if start < 0:
                start = 0

        self.end = stop
        if self.cutmode == '직접 스트림 복사':
            self.begin = self.getframe('key', start)
            if self.begin == self.end:
                self.begin = start

        else:
            self.begin = start if arg == '이후' else self.getframe('nearest', start)

        self.begin_end = arg
        self.duration = ''
        self.task = 'preview'
        basename = os.path.basename(self.path)
        ext = os.path.splitext(basename)[1]
        basename_ = f'preview{ext}'
        # self.addoutput()
        self.path_2 = f'{self.savedir}\\{basename_}'
        wavefile = f'{self.savedir}\\preview.wav'
        plt.close()
        if os.path.isfile(wavefile):
            os.remove(wavefile)

        caption = f'현 위치 {arg} {self.preview_duration}초 미리보기'
        self.progrdlg = wx.GenericProgressDialog(caption, caption,
                                                 maximum=100, parent=self,
                                                 style=0 | wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT)

        self.worker = k_losslesscut2.WorkerThread(self)
        self.worker.daemon = True
        self.worker.start()

        self.setcontrols5()
        self.dvlcSplitlist.UnselectAll()

    def getframe(self, kind, start):
        if kind == 'key':
            if self.pts['keyframes_all'] and (self.pos / 1000) in self.pts['keyframes_all']:
                return self.pos / 1000

        intervals = f'{start}%+'
        if kind == 'key':
            intervals += f'{self.millisec_per_frame / 1000}'
        elif kind == 'nearest':
            if self.keyframe_interval_avg == -1:
                intervals += f'{15 + self.millisec_per_frame / 1000}'
            else:
                intervals += f'{1.5 * self.keyframe_interval_avg + self.millisec_per_frame / 1000}'

        cmd = f'{FFPROBE} ' \
              f'-read_intervals {intervals} -v error ' \
              f'-select_streams v -show_entries frame=pts_time -of csv=p=0'.split() + [self.path]
        # print(' '.join(cmd))
        output = run(cmd, capture_output=True, text=True, creationflags=0x08000000)
        result = output.stdout.replace(',', '').split()
        timestamps = [float(x) for x in result]
        if kind == 'key':
            return timestamps[0]
        elif kind == 'nearest':
            return min(timestamps, key=lambda x: abs(start - x))

    def setcontrols5(self):
        self.slider_2.SetValue(0)
        self.slider_2.Disable()
        self.btnPrevSegment.Disable()
        self.btnGotoBegin2_2.Disable()
        self.btnZero_2.Disable()
        self.btnPlayEOF.Disable()
        self.btnNextSegment.Disable()
        self.stPos_2.SetLabel('')
        self.st3_2.SetLabel('')
        self.stDuration_2.SetLabel('')
        self.statusBar.SetStatusText('', 0)

    def onsaveas(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'saveas'
        k_losslesscut2.doit(self, event=evt)

    def onextractaudio(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'extractaudio'
        k_losslesscut2.doit(self, event=evt)

    def onremoveaudio(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'removeaudio'
        k_losslesscut2.doit(self, event=evt)

    def onncut(self, evt=None):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'ncut'
        k_losslesscut2.doit(self, event=evt)

    def ontcut(self, evt=None):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'tcut'
        k_losslesscut2.doit(self, event=evt)

    def onreencode(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'reencode'
        k_losslesscut2.doit(self, event=evt)

    def hasvideo(self):
        if self.player.get_state() != vlc.State.NothingSpecial:
            info = k_losslesscut2.getmediainfo(self.path)
            if not info[0] or info[3] in ['png', 'mjpeg']:
                caption = self.task_label[self.task]
                wx.MessageBox(f'비디오 스트림이 없는 파일입니다.\n\n{self.path}',
                              caption, wx.ICON_EXCLAMATION)
                return False

        return True

    def onrotate(self, evt=None):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        if evt:
            self.task = 'rotate'
            k_losslesscut2.doit(self, event=evt)
            return

        choices = ['회전(90° 반시계 방향)', '회전(90° 시계 방향)', '회전(180°)', '뒤집기(좌우)', '뒤집기(상하)',
                   '회전(90° 반시계 방향) + 뒤집기(상하)', '회전(90° 시계 방향) + 뒤집기(상하)']
        dlg = wx.SingleChoiceDialog(None, "선택하세요.", self.task_label[self.task], choices)
        val = dlg.ShowModal()
        dlg.Destroy()
        if val == wx.ID_OK:
            self.subtask = dlg.GetSelection()
            k_losslesscut2.doit(self, caption=f'{self.task_label[self.task]}')

    def ontransform(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        if not self.hasvideo():
            return

        dlg = k_losslesscut2.TransformDialog(self)
        val = dlg.ShowModal()
        dlg.Destroy()
        if val == wx.ID_OK:
            self.task = 'orientation'
            k_losslesscut2.doit(self, caption='가로형/세로형 변환')

    def onratio(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        if not self.hasvideo():
            return

        self.task = 'ratio'
        width, height = self.player.video_get_size()
        gcd = math.gcd(width, height)
        ratio = f'{int(width / gcd)}:{int(height / gcd)}'
        ratio_ = width / height
        message = f'종횡비(너비:높이)를 선택하세요.\n※ 너비({width})만 바뀜. 높이({height}) 불변' \
                  f'\n<= 영상의 좌·우 크롭\n\n(현재 종횡비: {ratio})'
        choices = ['32:9', '2.77:1', '2.55:1', '22:9', '21:9', '11:5', '20:9', '39:18', '19:9',
                   '37:18', '18:9', '19:10', '13:7', '16:9', '1.73:1(√3:1)', '5:3', '8:5',
                   '14:9', '3:2', '1.41:1(√2:1)', '11:8', '4:3', '5:4', '1:1', '2:3', '9:16']
        choices_ = []
        for x in choices:
            if '(' in x:
                w, h = x.split('(')[0].split(':')
                if float(w) / float(h) > ratio_:
                    continue
                choices_.append(x.split('(')[0])
            else:
                w, h = x.split(':')
                if float(w) / float(h) > ratio_:
                    continue
                choices_.append(x)

        dlg = wx.SingleChoiceDialog(None, message, self.task_label[self.task], choices_)
        val = dlg.ShowModal()
        dlg.Destroy()
        if val == wx.ID_OK:
            choice = dlg.GetStringSelection()
            width, height = choice.split(':')

            basename = os.path.basename(self.path)
            name, ext = os.path.splitext(basename)
            basename_ = f'[ratio {width.strip()}to{height}]{name}{ext}'
            self.outfile = rf'{self.savedir}\{basename_}'

            self.size = [width.strip(), height]
            k_losslesscut2.doit(self, caption=f'{self.task_label[self.task]}')

    def oncapture(self, evt):
        if self.just_after_popupmenu:
            self.just_after_popupmenu = False

        self.task = 'capture'
        caption = self.task_label[self.task]
        if self.player.get_state() == vlc.State.Ended:
            wx.MessageBox('비디오 재생이 끝났습니다. 재생 중일 때 캡처 해주세요.\n\n ',
                          caption, wx.ICON_EXCLAMATION)
            return False

        if self.player.get_state() != vlc.State.Paused:
            self.pause()

        width, height = self.player.video_get_size()

        h = [4320, 2160, 1440, 1080, 720, 480, 360, 240, 114]
        choices = []
        for x in h:
            if x <= height:
                choices.append(f'{int(width * x / height)}x{x}')

        if f'{width}x{height}' not in choices:
            choices.insert(0, f'{width}x{height}')

        message = f'이미지 해상도를 선택하세요.\n\n(비디오 해상도: {width}x{height})'
        dlg = wx.SingleChoiceDialog(self, message, self.task_label[self.task], choices)
        val = dlg.ShowModal()
        dlg.Destroy()
        if val == wx.ID_OK:
            choice = dlg.GetStringSelection()
            width, height = choice.split('x')
            basename = os.path.basename(self.path)
            name, ext = os.path.splitext(basename)
            basename_ = f'[capture]{name} {width}x{height}.jpg'
            self.outfile = rf'{self.savedir}\{basename_}'
            self.player.video_take_snapshot(0, self.outfile, int(width), int(height))
            # time.sleep(0.1)
            wx.PostEvent(self, k_losslesscut2.ResultEvent(f'finished-{self.task}'))

    def setcontrols(self):
        self.slider.Disable()
        self.disable5buttons()
        self.btnGotoBegin2.Disable()
        self.btnPrev10.Disable()
        self.btnPrev1.Disable()
        self.btnPrevFrame.Disable()
        self.btnPrevKey.Disable()
        self.btnZero.Disable()
        self.btnZeroClone.Disable()
        self.btnStop.Disable()
        self.btnPlaySection.Disable()
        self.btnNextKey.Disable()
        self.btnNextFrame.Disable()
        self.btnNext1.Disable()
        self.btnNext10.Disable()
        self.btnGotoBegin.Disable()
        self.btnGotoEnd.Disable()
        self.btnNearFrame.Disable()

        if self.just_after_openassource:
            self.just_after_openassource = False
        else:
            if self.player_2.get_state():
                self.player_2.pause()

            self.setcontrols_2()

    def setcontrols_2(self):
        self.slider_2.SetValue(0)
        self.slider_2.Disable()
        self.btnPrevSegment.Disable()
        self.btnNextSegment.Disable()
        self.btnGotoBegin2_2.Disable()
        self.btnZero_2.Disable()
        self.btnPlayEOF.Disable()
        self.stPos_2.SetLabel('')
        self.st3_2.SetLabel('')
        self.stDuration_2.SetLabel('')
        self.dvlcSplitlist.UnselectAll()
        self.btnSplitList.Disable()
        self.dvlcCutofflist.UnselectAll()
        self.btnCutoffList.Disable()
        self.btnPrevFile.Disable()
        self.btnNextFile.Disable()
        self.btnOpenAsSource.Disable()
        self.btnOpenDir.Disable()
        self.btnDefaultApp.Disable()
        self.btnWaveform.Disable()

    def setcontrols3(self, arg=None):
        boolean = ('keyframes_all' in self.pts) if self.cutmode == '직접 스트림 복사' else True
        self.btnSetBegin.Enable(boolean)
        self.btnSetEnd.Enable(boolean)
        if self.begin_end != '이후':
            self.btnGotoBegin.Enable()

        if self.begin_end != '이전':
            self.btnGotoEnd.Enable()

        if self.stBegin.GetLabel() and self.stEnd.GetLabel():
            if self.stBegin.GetLabel() == self.stEnd.GetLabel():
                self.btnCutoff.Disable()
            else:
                if not arg:
                    self.btnCutoff.Enable()
                    self.btnCutoff.SetToolTip(f'지정된 구간({self.stBegin.GetLabel()} ~ {self.stEnd.GetLabel()}) 추출')

        elif self.stBegin.GetLabel() or self.stEnd.GetLabel():
            if (self.stBegin.GetLabel() and getseconds(self.stBegin.GetLabel()) * 1000 == self.length) or \
                    (self.stEnd.GetLabel() and getseconds(self.stEnd.GetLabel()) == 0):
                self.btnCutoff.Disable()
            else:
                self.btnCutoff.Enable()
                self.btnCutoff.SetToolTip(f'지정된 구간({self.stBegin.GetLabel()} ~ {self.stEnd.GetLabel()}) 추출')

        self.togglebtncutoff()

    def setcontrols2(self, arg):
        delta = self.millisec_per_frame / 2.000001
        self.btnPrev10.Enable(arg and self.pos - delta > 10000)
        self.btnPrev1.Enable(arg and self.pos - delta > 1000)
        if 'frame-1st' in self.pts:
            self.btnPrevFrame.Enable(arg and self.pos - delta > self.pts['frame-1st'] * 1000)
        else:
            self.btnPrevFrame.Enable(arg and self.pos > 0)

        if 'key-1st' in self.pts:
            self.btnPrevKey.Enable(arg and self.pos - delta > self.pts['key-1st'] * 1000)
        else:
            self.btnPrevKey.Enable(arg and self.pos > 0)

        if 'key-reverse-1st' in self.pts:
            self.btnNextKey.Enable(arg and self.pos + delta < self.pts['key-reverse-1st'] * 1000)
        else:
            self.btnNextKey.Enable(arg and self.pos < self.length)

        if 'frame-reverse-1st' in self.pts:
            self.btnNextFrame.Enable(arg and self.pos + delta < self.pts['frame-reverse-1st'] * 1000)
        else:
            self.btnNextFrame.Enable(arg and self.pos < self.length)

        self.btnNext1.Enable(arg and self.pos + delta < self.length - 1000)
        self.btnNext10.Enable(arg and self.pos + delta < self.length - 10000)
        self.btnNearFrame.Enable(
            self.player.get_state() == vlc.State.Paused and not self.btnNextFrame.GetToolTip().Tip.startswith(
                '다음') and 'all' in self.pts and (self.pos / 1000) not in self.pts)
        self.btnGotoBegin2.Enable(self.pos != 0)
        self.btnGotoBegin.Enable(self.stBegin.GetLabel() != '')
        self.btnGotoEnd.Enable(self.stEnd.GetLabel() != '')

    def setcontrols_start(self, arg):
        self.btnPrev10.Enable(arg and self.pos >= 10000)
        self.btnPrev1.Enable(arg and self.pos >= 1000)
        self.btnPrevFrame.Enable(arg and self.pos != 0 and self.millisec_per_frame != -1)
        self.btnPrevKey.Enable(arg and self.pos > 0)

    def setcontrols_finish(self, arg):
        self.btnNextKey.Enable(arg and self.pos < self.length)
        self.btnNextFrame.Enable(arg and self.pos < self.length)
        self.btnNext1.Enable(arg and self.pos < self.length - 1000)
        self.btnNext10.Enable(arg and self.pos < self.length - 10000)

    def reset(self):
        self.length = -1
        self.pos = 0
        self.begin2 = -1
        self.end2 = -1
        self.millisec_per_frame = -1
        self.file0 = ''
        self.begin_end = ''
        self.mediainfo = {}
        self.begin_list = []
        self.end_list = []
        self.prev_begin_list = []
        self.prev_end_list = []
        self.split_list = []
        self.pts = {}

        self.gauge.SetValue([0, 0])
        self.gauge.Refresh()
        self.stPosLabel.SetLabel('')
        self.stPos.SetLabel('')
        self.st3.SetLabel(' ')
        self.stDuration.SetLabel('')
        self.stDurationLabel.SetLabel('')
        self.SetTitle(f'{TITLE}   {self.path}')
        self.btnSetBegin.SetBackgroundColour('silver')
        self.btnSetBegin.SetForegroundColour('red')
        self.btnSetBegin.SetWindowStyleFlag(wx.SIMPLE_BORDER)
        self.btnSetEnd.SetBackgroundColour('silver')
        self.btnSetEnd.SetForegroundColour('red')
        self.btnSetEnd.SetWindowStyleFlag(wx.SIMPLE_BORDER)
        self.setcontrols2(False)
        self.slider.SetValue(0)
        # bmp = wx.Bitmap('data/key2.png')
        # self.btnPrevKey.SetBitmap(bmp)
        # self.btnNextKey.SetBitmap(bmp)
        self.btnPrevKey.SetLabel('◁k')
        self.btnNextKey.SetLabel('k▷')
        self.stDuration.SetLabel('')
        self.stBegin.SetLabel('')
        self.btnCutoff.SetBackgroundColour('silver')
        self.btnCutoff.SetForegroundColour('black')
        self.btnCutoff.SetWindowStyleFlag(wx.SIMPLE_BORDER)
        self.stEnd.SetLabel('')
        self.stInfo.SetLabel('')
        self.statusBar.SetStatusText('', 0)
        self.statusBar.SetStatusText('', 1)
        self.statusBar.SetStatusText('', 2)
        self.updatetooltip2(1)

        self.btnPrevSegment.Enable(len(self.split_list) > 0 and self.dvlcSplitlist.GetSelectedRow() != 0)
        self.btnNextSegment.Enable(
            len(self.split_list) > 0 and self.dvlcSplitlist.GetSelectedRow() != len(self.split_list) - 1)
        self.btnSplitList.Enable(len(self.split_list) > 0)
        self.dvlcCutofflist.UnselectAll()
        self.btnCutoffList.Enable(len(self.cutoff_list[self.path]) > 0 if self.path in self.cutoff_list else False)
        self.btnPrevFile.Enable(len(self.output_list) > 0)
        self.btnNextFile.Enable(len(self.prevfile_list) > 0)
        self.inner.Hide(self.bsizer)
        self.inner.Hide(self.bsizer_2)
        self.inner.Show(self.bsizer0)
        self.setcontrols()

        self.menu1.Enable(103, True)
        self.menu2.Enable(201, True)
        self.menu2.Enable(202, True)
        self.menu2.Enable(214, True)  # 메뉴: '인코딩...'
        self.menu_audio.Enable(True)  # 메뉴: '오디오 처리'
        # self.menu2.Enable(206, True)   # 메뉴: '해상도 변경...'
        self.menu_ntcut.Enable(True)  # 메뉴: '분할'
        self.menu2.Enable(213, True)  # 메뉴: '인코딩...'
        self.menu2.Enable(212, True)  # 메뉴: '가로형/세로형 변환...'
        self.menu2.Enable(216, True)  # 메뉴: '종횡비 변경...'
        self.menu2.Enable(211, True)  # 메뉴: '캡처...'
        self.menu2.Enable(217, 'key-beginning' in self.pts and len(self.pts['key-beginning']))  # 메뉴: '키프레임 타임스탬프...'
        self.menu2.Enable(290, True)  # 메뉴: '미디어 정보...'

        if self.info[0] != '':  # 비디오 스트림이 있으면
            self.getframesall()

    def reset_2(self):
        self.length_2 = -1
        self.pos_2 = 0
        self.stPos_2.SetLabel('')
        self.st3_2.SetLabel(' ')
        self.stDuration_2.SetLabel('')
        self.slider_2.SetValue(0)
        self.menu_audio.Enable()
        # self.menu2.Enable(206,True)
        self.menu_ntcut.Enable()
        self.menu2.Enable(213, True)
        self.menu2.Enable(214, True)
        self.menu2.Enable(290, True)
        if self.task in ['music3', 'concat2']:
            self.menu1.Enable(103, True)
            self.menu2.Enable(201, True)
            self.menu2.Enable(202, True)
            self.menu_audio.Enable(self.info_2[0] != '')  # 메뉴: '오디오 처리'

    def onclose(self, evt):
        self.Close()

    def onwindowclose(self, evt):
        with open('config.pickle', 'wb') as f:
            pickle.dump(self.config, f)

        if plt.get_fignums():
            plt.close()

        if self.helf_frame:
            self.helf_frame.Close()

        if self.player:
            self.player.stop()

        if self.player_2:
            self.player_2.stop()

        # 프로세스 종료
        if self.proc:
            try:
                Popen(f'TASKKILL /F /PID {self.proc.pid} /T'.split(), creationflags=0x08000000)
            except Exception as e:
                print(e)

        # 프로그램 실행 중 생성된 explorer.exe 끝내기
        procs = [proc for proc in psutil.process_iter(['name', 'pid'])
                 if proc.info['name'] == 'explorer.exe']
        for proc in procs:
            if  proc.info['pid'] not in self.pids_explorer_existing:
                try:
                    proc.terminate()
                except Exception as e:
                    print(e)

        # 임시파일 삭제
        path = f'{self.savedir}\\preview.mp4'
        if os.path.isfile(path):
            try:
                os.remove(path)
            except Exception as e:
                print(e)

        p = re.compile('\.wav$')
        filenames = os.listdir(self.savedir)
        for filename in filenames:
            m = p.search(filename)
            if m:
                path = f'{self.savedir}\\{filename}'
                try:
                    os.remove(path)
                except Exception as e:
                    print(e)

        self.Destroy()


if __name__ == '__main__':
    app = wx.App()
    Frame = VideoCut(None)
    Frame.Show()
    app.MainLoop()
