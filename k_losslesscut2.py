# -*- coding: utf-8 -*-
import datetime
import pickle
import math
from subprocess import Popen, PIPE, run
import threading
from threading import Thread
import ctypes
import os
import wx
import wx.html
import wx.html2
from wx.lib.agw.floatspin import FloatSpin
from wx.lib.dialogs import ScrolledMessageDialog
import webbrowser
from pprint import pformat
import json
import re
import wx.lib.wxpTag
import time

from wx.py.shell import Shell

FFMPEG = os.getcwd() + r'\ffmpeg.exe'
FFPROBE = os.getcwd() + r'\ffprobe.exe'

import vlc
"""
vlc.State
{0: 'NothingSpecial',
 1: 'Opening',
 2: 'Buffering',
 3: 'Playing',
 4: 'Paused',
 5: 'Stopped',
 6: 'Ended',
 7: 'Error'}        
"""

TITLE = 'K-LosslessCut'
CUTMODE = '직접 스트림 복사'
OPEN_ERROR = '파일 형식이 지원되지 않거나, 파일 확장명이 올바르지 않거나, 파일이 손상되었을 수 있습니다.'
FILENAME_LIMIT = 40

VERSION = '2024.09.09'
PYTHON = '3.10.7'
WXPYTHON = '4.2.1'
FFMPEG2 = 'ffmpeg-2022-05-23-git-6076dbcb55'
VLC = '3.0.20'
PYINSTALLER = '5.6.2'


def xtimedelta(milliseconds):
    t = round(milliseconds)
    s = str(datetime.timedelta(milliseconds=t))
    idx = s.find('.')
    if idx == -1:
        return s + '.000'
    else:
        return s[:idx+4]


def getseconds(s):
    sec = -1
    if s.count(':') == 2:
        h, m, s = s.split(':')
        sec = int(h)*3600 + int(m)*60 + float(s)
    elif s.count(':') == 1:
        m, s = s.split(':')
        sec = int(m)*60 + float(s)

    return sec


class ResultEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(-1)
        self.data = data


class WorkerThread2(Thread):
    def __init__(self, parent):
        Thread.__init__(self)
        self.parent = parent

    def run(self):
        parent = self.parent
        if parent.task2 == 'pts-all':
            # 전체 키프레임
            cmd = f'{FFPROBE} ' \
                  f'-select_streams v -show_entries packet=pts_time,flags -of csv=p=0'.split() + [parent.path]
            # print(' '.join(cmd))
            output = run(cmd, capture_output=True, text=True, creationflags=0x08000000)
            result = re.findall('(\d+\.\d{6}),K', output.stdout)
            pts = [round(float(x), 3) for x in result]
            pts.sort()

            # 맨처음 키프레임
            parent.pts['key-1st'] = pts[0]
            parent.pts['key-2nd'] = pts[1]

            # 맨끝 키프레임
            parent.pts['key-reverse-1st'] = pts[-1]
            parent.pts['key-reverse-2nd'] = pts[-2]

            parent.pts['keyframes_all'] = pts
            parent.pts['keyframes_all_reverse'] = sorted(pts, reverse=True)

            pts_2 = [float(x) for x in result]
            pts_2.sort()
            parent.pts['keyframes_all2'] = pts_2

            # 시작부분 키프레임
            pts_ = [x for x in pts if x < parent.keyframes_pts_range]
            parent.pts['key-beginning'] = pts_
            parent.menu2.Enable(217, True)

            if len(pts_) > 1:
                gaps = {}
                x_ = pts_[0]
                for x in pts_[1:]:
                    gap = round(x - x_, 6)
                    if gap in gaps:
                        gaps[gap] += 1
                    else:
                        gaps[gap] = 1
                    x_ = x

                parent.keyframe_interval_avg = max(gaps, key=gaps.get)

            # bmp = wx.Bitmap('src/key.png')
            # parent.btnPrevKey.SetBitmap(bmp)
            # parent.btnNextKey.SetBitmap(bmp)
            parent.btnPrevKey.SetLabel('◁K')
            parent.btnNextKey.SetLabel('K▷')

            # 전체 프레임
            # cmd = f'{FFPROBE} ' \
            #       f'-select_streams v -show_entries packet=pts_time -of csv=p=0'.split() + [parent.path]

            # output = run(cmd, capture_output=True, text=True, creationflags=0x08000000)
            result = re.findall('(\d+\.\d{6})', output.stdout)
            pts2 = [round(float(x), 3) for x in result]
            pts2.sort()
            parent.pts['all'] = pts2

            pts2_2 = [float(x) for x in result]
            pts2_2.sort()
            parent.pts['all2'] = pts2_2
            # print(parent.pts['all'])
            parent.pts['frame-1st'] = pts2[0]
            parent.pts['frame-2nd'] = pts2[1]
            parent.pts['frame-reverse-1st'] = pts2[-1]
            parent.pts['frame-reverse-2nd'] = pts2[-2]
            parent.btnPrevFrame.SetLabel('◁F')
            parent.btnNextFrame.SetLabel('F▷')

            # print("pts", parent.pts)
            # print(f'"getPtsAll" finished. {time.time() - t0}초')

        elif parent.task2 == 'find-nearest-frame':
            intervals = f'{parent.pos/1000}%+{1.5*parent.keyframe_interval_avg + 0.05}'
            cmd = f'{FFPROBE} -read_intervals {intervals} ' \
                  f'-select_streams v -show_entries packet=pts_time -of csv=p=0'.split() + [parent.path]
            # print(' '.join(cmd))
            output = run(cmd, capture_output=True, text=True, creationflags=0x08000000)
            result = re.findall('(\d+\.\d{6})', output.stdout)
            pts = [float(x) for x in result]
            pts.sort()
            # print(pts[0], '~', pts[-1], pts)
            if parent.pos/1000 > pts[-1]:
                # print(parent.pos/1000, '(pos) =>', parent.pos/1000, '(pos 그대로)', 'length:', parent.length)
                parent.player.set_position(parent.pos / parent.length)
            else:
                nearest_pts = min(pts, key=lambda x: abs(parent.pos/1000 - x))
                # print(parent.pos/1000, '(pos) =>', nearest_pts, '(nearest_pts)', 'length:', parent.length)
                parent.player.set_position(nearest_pts*1000 / parent.length)

            parent.media_position_changed()
            parent.setcontrols2(True)
            parent.pts['current'] = pts

        elif parent.task2 == 'kill-vlc':
            time.sleep(1)
            try:
                Popen(f'TASKKILL /F /IM vlc.exe /T', creationflags=0x08000000)
            except ValueError:
                pass

        """
        elif parent.task2 == 'extract-frame':
            start = parent.pos/1000
            outfile = f'{parent.savedir}\\[{parent.task2}]'
            command = f'{FFMPEG} -ss {start} -t 0.001 -i {parent.infile3} -r 1 -s 640x360 ' \
                      f'{outfile}frame-%d.jpg'.split()
            output = check_output(command, creationflags=0x08000000)
            parent.path_2 = f'{outfile}frame-1.jpg'
            wx.PostEvent(parent, ResultEvent(f'finished-{parent.task2}'))
        """

        """
            # 특정 구간 키프레임 이미지 추출
            cmd = f'powershell & "{FFMPEG}" -y -ss 0 -i \'{parent.infile}\' -t 100 ' \
                  f'-vf scale=\'-1:1\',select=\'eq(pict_type\,I)\' -fps_mode passthrough -r 1000 -frame_pts 1 ' \
                  f'\'{parent.tempdir}/%d.png\' 2>&1 | % ToString'
        """


class WorkerThread(Thread):
    def __init__(self, parent):
        Thread.__init__(self)
        self.parent = parent
        self.abort = False
        self.has_video = False
        self.has_audio = False
        self.section = ''
        self.path_short = ''
        self.kind = ''
        self.serial = ''
        self.infile_short = ''
        self.ws = ' ' * 6
        self.segment_short = ''
        self.file = os.path.split(parent.path)[1]
        self.lufs = ''
        self.volume = ''
        self.audio_bitrate = ''
        self.pic = ''
        self.audio = ''
        self.encoding = ''
        self.rotate = ''
        self.ratio = ''
        self.orientation = ''
        self.file_short = os.path.split(parent.infile)[1] + \
                            (('…' + os.path.splitext(parent.infile)[1])
                             if len(os.path.split(parent.infile)[1]) > FILENAME_LIMIT else '')
        self.infile2_short = ''
        self.duration = ''

    def run(self):
        parent = self.parent
        parent.duration = ''
        if not parent.infile and parent.path:
            parent.infile = parent.path

        self.file = f'{self.file_short}'

        cmd = ''
        if parent.task in ['ncut', 'tcut']:
            self.kind = f'{parent.segmentnum}개' if parent.task == 'ncut' else f'{int(parent.segmentlen/1000)}초'
            self.serial = f'#{parent.segmentcount}/{parent.segmentnum}'
            self.infile_short = os.path.split(parent.infile)[1][:FILENAME_LIMIT] + \
                                  (('…' + os.path.splitext(parent.infile)[1])
                                   if len(os.path.split(parent.infile)[1]) > FILENAME_LIMIT else '')
            end = parent.begin + parent.segmentlen
            if end > parent.length2:
                end = parent.length2

            basename = os.path.basename(parent.infile)
            name, ext = os.path.splitext(basename)

            parent.outfile = f'{parent.savedir}\\[{parent.task}]{name} ({parent.segmentcount}){ext}'

            parent.segments.append(parent.outfile)
            if parent.cutmode == '직접 스트림 복사':
                cmd = f'powershell & "{FFMPEG}" -y -ss {parent.begin / 1000} -i'.split() + \
                      [f'"{parent.infile}"'] + \
                      f'-to {end / 1000} -c copy -copyts -avoid_negative_ts make_zero -map 0'.split() + \
                      [f'"{parent.outfile}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()
            else:
                if parent.cbFade.GetValue():
                    duration = end/1000 - parent.begin/1000
                    vf = ''
                    if parent.fade_duration * 2 < duration:
                        fade_st = duration - parent.fade_duration
                        vf = f'-vf "fade=t=in:st=0:d={parent.fade_duration},' \
                             f'fade=t=out:st={fade_st}:d={parent.fade_duration}"' if parent.fade_duration else ''

                    if vf:
                        cmd = f'powershell & "{FFMPEG}" -y -ss {parent.begin / 1000} -i'.split() + \
                              [f'"{parent.infile}"'] + \
                              f'-t {duration} {vf} -force_key_frames \'expr:gte(t,n_forced*{parent.keyframe_interval})\' -preset fast'.split() + \
                              [f'"{parent.outfile}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()
                    else:
                        cmd = f'powershell & "{FFMPEG}" -y -ss {parent.begin / 1000} -i'.split() + \
                              [f'"{parent.infile}"'] + \
                              f'-t {end/1000 - parent.begin/1000}'.split() + \
                              [f'"{parent.outfile}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()
                              # f'-t {end/1000 - parent.begin/1000} -force_key_frames \'expr:gte(t,n_forced*{parent.keyframe_interval})\' -acodec copy'.split() + \
                else:
                    cmd = f'powershell & "{FFMPEG}" -y -ss {parent.begin / 1000} -i'.split() + \
                          [f'"{parent.infile}"'] + \
                          f'-t {end/1000 - parent.begin/1000}'.split() + \
                          [f'"{parent.outfile}"'] + \
                          '2>&1 | % ToString | Tee-Object out.txt'.split()
                          # f'-t {end/1000 - parent.begin/1000} -force_key_frames \'expr:gte(t,n_forced*{parent.keyframe_interval})\' -acodec copy'.split() + \

            # print('task:', parent.task, 'cmd:', ' '.join(cmd))
            parent.proc = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, creationflags=0x08000000)
            while parent.proc.poll() is None and not self.abort:
                self.checkprogress()

        else:
            if parent.task in ['preview', 'cutoff']:
                self.section = f'{xtimedelta(parent.begin * 1000) } - {xtimedelta(parent.end * 1000)}'
                self.path_short = os.path.split(parent.path)[1][:FILENAME_LIMIT] + \
                                  (('…' + os.path.splitext(parent.path)[1])
                                   if len(os.path.split(parent.path)[1]) > FILENAME_LIMIT else '')
                try:
                    idx = parent.pts['all'].index(parent.end)
                except ValueError:
                    try:
                        idx = parent.pts['all2'].index(parent.end)
                    except ValueError:
                        idx = -1

                end = parent.pts['all2'][idx] if idx != -1 else parent.end
                duration = end - parent.begin
                if parent.cutmode == '직접 스트림 복사':
                    end -= parent.millisec_per_frame/1000 * 0.45
                    cmd = f'powershell & "{FFMPEG}" -y -ss {parent.begin} -i'.split() + \
                          [f'"{parent.path}"'] + \
                          f'-to {end} -c copy -copyts -avoid_negative_ts make_zero -map 0'.split() + \
                          [f'"{parent.path_2}"'] + \
                          '2>&1 | % ToString | Tee-Object out.txt'.split()
                else:
                    if parent.cbFade.GetValue():
                        fade_duration = parent.fade_duration
                        fade_st = duration - fade_duration
                        vf = ''
                        af = ''
                        if parent.task == 'preview':
                            if fade_duration > duration:
                                fade_duration = duration
                                fade_st = duration - fade_duration

                            vf = f'-vf "fade=t=in:st=0:d={fade_duration},' \
                                 f'fade=t=out:st={fade_st}:d={fade_duration}"' if parent.fade_duration else ''

                            if parent.begin_end == '이후':
                                af = f'-af "afade=t=in:st=0:d={fade_duration}"' if parent.fade_duration else ''

                            elif parent.begin_end == '이전':
                                af = f'-af "afade=t=out:st={fade_st}:d={fade_duration}"' if parent.fade_duration else ''

                        elif parent.task == 'cutoff':
                            if fade_duration * 2 > duration:
                                fade_duration = duration / 2
                                fade_st = duration - fade_duration

                            vf = f'-vf "fade=t=in:st=0:d={fade_duration},' \
                                 f'fade=t=out:st={fade_st}:d={fade_duration}"' if parent.fade_duration else ''

                            af = f'-af "afade=t=in:st=0:d={fade_duration},' \
                                 f'afade=t=out:st={fade_st}:d={fade_duration}"' if parent.fade_duration else ''

                        cmd = f'powershell & "{FFMPEG}" -y -ss {parent.begin} -i'.split() + \
                              [f'"{parent.path}"'] + \
                              f'-t {duration} {vf} {af}'.split() + \
                              [f'"{parent.path_2}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()
                              # f'-t {duration} {vf} -force_key_frames \'expr:gte(t,n_forced*{parent.keyframe_interval})\' -acodec copy'.split() + \
                    else:
                        cmd = f'powershell & "{FFMPEG}" -y -ss {parent.begin} -i'.split() + \
                              [f'"{parent.path}"'] + \
                              f'-t {duration}'.split() + \
                              [f'"{parent.path_2}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()
                              # f'-t {duration} -force_key_frames \'expr:gte(t,n_forced*{parent.keyframe_interval})\' -acodec copy'.split() + \

                # print('task:', parent.task, 'cmd:', ' '.join(cmd))

            elif parent.task == 'lufs':
                plus = '↑' if parent.voladjust > 0 else ('↓' if parent.voladjust < 0 else '')
                voladjust = f' {plus}{round(abs(parent.voladjust), 2)}dB' if parent.voladjust !=0 else ''
                self.lufs = f'[LUFS 측정]{voladjust}'

                cmd = f'powershell & "{FFMPEG}" -i'.split() + \
                      [f'"{parent.infile}"'] + \
                      '-af ebur128=framelog=verbose -f null -'.split() + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()
                      # '-af ebur128=metadata=1 -f null -'.split() + \
                      # '-af ebur128=framelog=verbose -f null -'.split() + \

            elif parent.task == 'measurevolume':
                cmd = f'powershell & "{FFMPEG}" -i'.split() + \
                      [f'"{parent.infile}"'] + \
                      '-af volumedetect -f null -'.split() + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'volume':
                plus = '↑' if parent.voladjust > 0 else ('↓' if parent.voladjust < 0 else '')
                voladjust = f' {plus}{round(abs(parent.voladjust), 2)}dB'
                self.volume = f'[볼륨 조정]{voladjust}'

                cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                      [f'"{parent.infile}"'] + \
                      f'-c:v copy -af volume={parent.voladjust}dB'.split() + \
                      [f'"{parent.outfile}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'saveas':
                cmd = f'powershell copy -LiteralPath "{parent.infile}" "{parent.outfile}"'.split() + \
                      '-Passthru 2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'orientation':
                self.orientation = f'[{parent.subtask}, {parent.direction}]'

                if parent.subtask == '세로형으로':
                    if parent.direction == '상·하 여백 넣기':
                        cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                              [f'"{parent.infile}"'] + \
                              '-vf "pad=iw:iw*(iw/ih):(ow-iw)/2:(oh-ih)/2" -c:a copy'.split() + \
                              [f'"{parent.outfile}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()

                    elif parent.direction == '좌·우 잘라 내기':
                        width, height = parent.player.video_get_size()
                        zoom = 1
                        cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                              [f'"{parent.infile}"'] + \
                              f'-vf "scale=-1:{width*zoom}:flags=lanczos,crop={height}:{width}" -c:a copy'.split() + \
                              [f'"{parent.outfile}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()
                              #'-vf crop=ih*ih/iw:ih -c:a copy'.split() + \

                elif parent.subtask == '가로형으로':
                    if parent.direction == '상·하 여백 넣기':
                        cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                              [f'"{parent.infile}"'] + \
                              '-vf crop=iw:iw*iw/ih -c:a copy'.split() + \
                              [f'"{parent.outfile}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()

                    elif parent.direction == '좌·우 잘라 내기':
                        cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                              [f'"{parent.infile}"'] + \
                              '-vf pad=ih*ih/iw:ih:ih*ih/iw/2-iw/2:0 -c:a copy'.split() + \
                              [f'"{parent.outfile}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'ratio':
                self.ratio = f'[종횡비 {parent.size[0]}:{parent.size[1]}]'

                ratio = float(parent.size[0]) / float(parent.size[1])
                cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                      [f'"{parent.infile}"'] + \
                      f'-vf crop={ratio}*ih:ih -c:a copy'.split() + \
                      [f'"{parent.outfile}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'rotate':
                choices = ['회전(90° 반시계 방향)', '회전(90° 시계 방향)', '회전(180°)', '뒤집기(좌우)', '뒤집기(상하)',
               '회전(90° 반시계 방향) + 뒤집기(상하)', '회전(90° 시계 방향) + 뒤집기(상하)']
                self.rotate = f'[{choices[parent.subtask]}]'

                vf = ['transpose=2', 'transpose=1', 'transpose=2,transpose=2',
                      'hflip', 'vflip', 'transpose=0', 'transpose=3'][parent.subtask]
                cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                      [f'"{parent.infile}"'] + \
                      f'-vf "{vf}" -codec:a copy'.split() + \
                      [f'"{parent.outfile}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'extractaudio':
                bitrate = parent.audio_bitrates[parent.audio_bitrate]
                self.audio_bitrate = f'비트레이트: {bitrate}'

                streams = {}
                if not parent.audio_bitrate:
                    try:
                        streams = get_streams(parent.infile)
                    except ValueError:
                        pass

                    audio_stream = [stream for stream in streams if stream["codec_type"] == "audio"]
                    bitrate = audio_stream[0]['bit_rate']

                cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                      [f'"{parent.infile}"'] + \
                      f'-c:a libmp3lame -b:a {bitrate}'.split() + \
                      [f'"{parent.outfile}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'removeaudio':
                self.audio = f'오디오 ✘'
                cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                      [f'"{parent.infile}"'] + \
                      '-map 0 -map -0:a -c copy'.split() + \
                      [f'"{parent.outfile}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'addaudio3':
                self.infile2_short = os.path.split(parent.infile2)[1][:FILENAME_LIMIT] + \
                                  (('…' + os.path.splitext(parent.infile2)[1])
                                   if len(os.path.split(parent.infile2)[1]) > FILENAME_LIMIT else '')
                self.audio = f'➕ {self.infile2_short}'
                info = getmediainfo(parent.infile)
                self.duration = info[8]
                info_2 = getmediainfo(parent.infile2)
                duration_2 = info_2[9]
                # info: 0=>resolution, 1=>timescale, 2=>pixelformat, 3=>videocodec, 4=>samplerate, 5=>channels, 6=>audio_codec, 7=>audio_bitrate, 8=>video_duration, 9=>audio_duration]
                # 오디오 스트림이 있으면
                samplerate = info[4]
                if samplerate:
                    times = math.ceil(float(self.duration) / float(duration_2))
                    size = float(duration_2) * int(samplerate)
                    cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                          [f'"{parent.infile}"', '-i', f'"{parent.infile2}"'] + \
                          f'-c:v copy -filter_complex "[1:a]aloop=loop={times-1}:size={size}[a1];[0:a][a1]amix=inputs=2[aout]" -map 0:v -map "[aout]" -shortest'.split() + \
                          [f'"{parent.outfile}"'] + \
                          '2>&1 | % ToString | Tee-Object out.txt'.split()
                    print(' '.join(cmd))
                # 오디오 스트림이 없으면
                else:
                    cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                          [f'"{parent.infile}"', '-i', f'"{parent.infile2}"'] + \
                          f'-c copy'.split() + \
                          [f'"{parent.outfile}"'] + \
                          '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'remux':
                cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                      [f'"{parent.infile}"'] + \
                      '-c copy -map 0'.split() + \
                      [f'"{parent.outfile}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task in ['waveform', 'waveform2']:
                self.section = f'{xtimedelta(0) } - {xtimedelta(parent.length_2 * 1000)}'
                self.path_short = os.path.split(parent.path)[1][:FILENAME_LIMIT] + \
                                  (('…' + os.path.splitext(parent.path)[1])
                                   if len(os.path.split(parent.path)[1]) > FILENAME_LIMIT else '')

                basename = os.path.basename(parent.path_2)
                name, ext = os.path.splitext(basename)
                begin = 0
                end = parent.length_2 / 1000
                outfile = ''
                if parent.task == 'waveform':
                    outfile = f'{parent.savedir}\\{name}.wav'
                    # print('parent.begin_end', parent.begin_end, 'begin', begin)
                    if parent.begin_end and parent.begin_end == '이전':    # 미리보기
                        begin = parent.length_2 / 1000 - parent.preview_duration
                    else:   # 구간추출
                        end = parent.preview_duration

                elif parent.task == 'waveform2':
                    outfile = f'{parent.savedir}\\{name}2.wav'
                    begin = parent.length_2 / 1000 - parent.preview_duration

                cmd = f'powershell & "{FFMPEG}" -y -ss {begin} -i'.split() + \
                      [f'"{parent.path_2}"'] + \
                      f'-to {end} -ac 1 -f wav'.split() + \
                      [f'"{outfile}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

                # print('task:', parent.task, 'cmd:', ' '.join(cmd))

            elif parent.task == 'concat':
                path = parent.segments[parent.segmentcount - 1]
                cmd = f'powershell & "{FFMPEG}" -i'.split() + \
                      [f'"{path}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'concat2':
                self.segment_short = os.path.split(parent.segments[0])[1][:FILENAME_LIMIT] + \
                                  (('…' + os.path.splitext(parent.segments[0])[1])
                                   if len(os.path.split(parent.segments[0])[1]) > FILENAME_LIMIT else '')

                file = parent.outfile if parent.task == 'concat2' else parent.path_2
                cmd = f'powershell & "{FFMPEG}" -y -f concat -safe 0 -i concat_list.txt -c copy'.split() + \
                      [f'"{file}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'music3':
                self.file = f'[오디오] {self.file_short}'
                self.pic = f'[이미지] {self.infile2_short}'

                cmd = f'powershell & "{FFMPEG}" -y -loop 1 -i'.split() + \
                      [f'"{parent.infile2}"', '-i', f'"{parent.infile}"'] + \
                      '-map 0 -map 1:a -c:v libx264 -tune stillimage -c:a copy -shortest'.split() + \
                      [f'"{parent.outfile}"'] + \
                      '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task in ['reencode', 'reencode2']:
                print(parent.task)
                path = parent.infile if parent.infile else parent.path
                info = getmediainfo(path)
                self.has_video = (info[0] != '')
                self.has_audio = (info[4] != '')

                paths_ = parent.reencode2_paths
                task = f'인코딩 #{len(paths_[-1][0])-len(paths_)+1}/{len(paths_[-1][0])}' \
                    if parent.task == 'reencode2' else '인코딩'

                config_ = parent.config
                video_info = f'{config_["resolution"]}, {config_["timescale"]} tbn, ' \
                             f'{config_["pixelformat"]}, {config_["videocodec"]}' \
                    if self.has_video else '스트림 없음'

                self.encoding = f'[{task}] 비디오: {video_info}, ' \
                           f'오디오: {config_["samplerate"]}Hz, {config_["channels"]}ch, ' \
                       f'{config_["audiocodec"]}'

                codec_ = {'h264':'libx264', 'h.264/avc':'libx264', 'h265':'libx265', 'h.265/hevc':'libx265',
                          'vp9':'libvpx-vp9'}
                resolution = config_['resolution']
                timescale = config_['timescale']
                pixelformat = config_['pixelformat']
                videocodec = codec_[config_['videocodec'].lower()]
                samplerate = config_['samplerate']
                channels = config_['channels']
                audiocodec = config_['audiocodec']

                if self.has_video:
                    if self.has_audio:
                        cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                              [f'"{parent.infile}"'] + \
                              f'-map 0:v -map 0:a -ac {channels} -c:a {audiocodec} -ar {samplerate} ' \
                              f'-vf format={pixelformat},scale={resolution},yadif ' \
                              f'-video_track_timescale {timescale} -c:v {videocodec}'.split() + \
                              [f'"{parent.outfile}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()
                    else:
                        cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                              [f'"{parent.infile}"'] + \
                              f'-f lavfi -i "anullsrc=r={samplerate}:cl={channels}:d=1" -map 0:v -map 1:a -ac {channels} -c:a {audiocodec} -ar {samplerate} ' \
                              f'-vf format={pixelformat},scale={resolution},yadif ' \
                              f'-video_track_timescale {timescale} -c:v {videocodec}'.split() + \
                              [f'"{parent.outfile}"'] + \
                              '2>&1 | % ToString | Tee-Object out.txt'.split()
                else:
                    cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
                          [f'"{parent.infile}"'] + \
                          f'-map 0:0 -ac {channels} -c:a {audiocodec} -ar {samplerate}'.split() + \
                          [f'"{parent.outfile}"'] + \
                          '2>&1 | % ToString | Tee-Object out.txt'.split()

            elif parent.task == 'saveas':
                self.infile_short = os.path.split(parent.infile)[1][:FILENAME_LIMIT]

            #print('task:', parent.task, 'cmd:', ' '.join(cmd))
            #print('task:', parent.task, 'cmd:', cmd)

            if parent.task_label[parent.task] != '':
                if parent.task == 'preview':
                    s = f'[현 위치 {parent.begin_end} {parent.preview_duration}초 미리보기 시작]'
                    parent.stInfo.SetLabel(f'{s}\n작업 대상: {parent.path}')

                else:
                    file = parent.path if parent.task in ['preview', 'cutoff'] else parent.infile
                    parent.stInfo.SetLabel(f'[{parent.task_label[parent.task]} 시작]\n작업 대상: {file}')
            else:
                parent.stInfo.SetLabel('')

            parent.proc = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, creationflags=0x08000000)

            if parent.task in ['preview', 'cutoff', 'lufs', 'measurevolume', 'volume',
                               'extractaudio', 'removeaudio', 'addaudio3', 'orientation',
                               'concat2', 'music3', 'reencode', 'reencode2', 'rotate',
                               'waveform', 'waveform2', 'remux', 'ratio']:
                while parent.proc.poll() is None and not self.abort:
                    self.checkprogress()

            elif parent.task == 'saveas':
                while parent.proc.poll() is None and not self.abort:
                    self.checkprogress2()

            elif parent.task == 'concat':
                while parent.proc.poll() is None and not self.abort:
                    self.checkprogress3()

    def get_cmd(self):
        parent = self.parent
        if parent.audio_bitrate:
            bitrate = parent.audio_bitrates[parent.audio_bitrate]
        else:
            try:
                streams = get_streams(parent.infile)
            except ValueError:
                return

            audio_stream = [stream for stream in streams if stream["codec_type"] == "audio"]
            bitrate = audio_stream[0]['bit_rate']

        cmd = f'powershell & "{FFMPEG}" -y -i'.split() + \
              [f'"{parent.infile}"'] + \
              f'-c:a libmp3lame -b:a {bitrate}'.split() + \
              [f'"{parent.outfile}"'] + \
              '2>&1 | % ToString | Tee-Object out.txt'.split()

        return cmd

    def raise_exception(self):
        thread_id = self.get_id()
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id,
              ctypes.py_object(SystemExit))

        if res > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
            print('예외 발생 실패')

    def get_id(self):
        if hasattr(self, '_thread_id'):
            return self._thread_id

        for t in threading.enumerate():
            if t is self:
                return t.native_id

    def checkprogress(self):
        parent = self.parent
        if parent.progrdlg.WasCancelled():
            self.abort = True
            wx.PostEvent(parent, ResultEvent(f'cancelled-{parent.task}'))
            self.raise_exception()
            return

        s = str(parent.proc.stdout.readline())
        # print(s)
        if 'Error initializing' in s:
            s = s.replace("b'", "").replace("\\r\\n'", "")
            self.abort = True
            wx.MessageBox(f'{s}\n\n{parent.infile}', 'Error', wx.ICON_ERROR)
            wx.PostEvent(parent, ResultEvent(f'cancelled-{parent.task}'))
            self.raise_exception()
            return

        if s == "b''":
            if not self.abort:
                self.abort = True
                wx.PostEvent(parent, ResultEvent(f'cancelled-{parent.task}'))
                self.raise_exception()
            return

        timestamp = ''
        speed = 0.0
        if parent.task == 'concat2':
            parent.duration = parent.totalduration

        if parent.duration:
            if 'time=' in s:
                # s => b'frame=    0 fps=0.0 q=0.0 size=       0kB time=00:00:00.34 bitrate=   1.1kbits/s speed=3.56x    \r\n'
                t = s.split('time=')[1].split('bitrate')[0].strip()
                if t:
                    if t.startswith('-'):
                        return

                    timestamp = t

                if s.split('speed=')[1].startswith('N/A'):
                    return

                # s => b'frame=    0 fps=0.0 q=0.0 size=       0kB time=00:00:00.34 bitrate=   1.1kbits/s speed=3.56x    \r\n'
                speed = s.split('speed=')[1].split('x')[0].strip()
        else:
            if 'Duration:' in s:
                if parent.task in ['music3', 'addaudio3']:
                    if parent.durationcount == 0:
                        parent.durationcount += 1
                        return

                # s => b'  Duration: 00:04:15.77, start: 0.000000, bitrate: 4901 kb/s\r\n'
                s2 = s.split(',')[0].split(': ')[1].strip()
                if s2.startswith('N/A'):
                    return

                if parent.task == 'addaudio3':
                    print(xtimedelta(float(self.duration) * 1000))
                    parent.duration = xtimedelta(float(self.duration) * 1000)
                else:
                    parent.duration = s2

            if parent.duration:
                timestamp = '00:00:00'

        if parent.duration and timestamp:
            if parent.task in ['preview', 'cutoff']:
                percent = round((getseconds(timestamp)/(parent.end - parent.begin)) * 100)
                if percent < 0:
                    return

                if percent > 100:
                    percent = 100

                msg = f'{self.path_short}\n[{parent.cutmode}] {self.section}\n{percent}%{self.ws}' \
                      f'{timestamp} / {xtimedelta((parent.end-parent.begin) * 1000)}{self.ws}{speed}배속'

                try:
                    parent.progrdlg.Update(percent, msg)
                except Exception as e:
                    print(e)

                if percent == 0:
                    parent.progrdlg.Center()

            elif parent.task in ['waveform', 'waveform2']:
                percent = round((getseconds(timestamp)/(parent.end - parent.begin)) * 100)
                if percent < 0:
                    return

                if percent > 100:
                    percent = 100

                msg = f'{self.path_short}\n[{parent.cutmode}] {self.section}\n{percent}%{self.ws}' \
                      f'{timestamp} / {xtimedelta(parent.length_2 * 1000)}{self.ws}{speed}배속'

                try:
                    parent.progrdlg.Update(percent, msg)
                except Exception as e:
                    print(e)

                if percent == 0:
                    try:
                        parent.progrdlg.Center()
                    except ValueError:
                        pass

            elif parent.task in ['ncut', 'tcut']:
                percent = round((getseconds(timestamp)*1000/parent.segmentlen)*100)
                if percent < 0:
                    return

                if percent > 100:
                    percent = 100

                # kind = f'{parent.segmentnum}개' if parent.task == 'ncut' else f'{int(parent.segmentlen/1000)}초'
                # serial = f'#{parent.segmentcount}/{parent.segmentnum}'
                msg = f'{self.infile_short}\n' \
                      f'[{parent.cutmode}] {self.kind} {self.serial}\n{percent}%{self.ws}' \
                      f'{timestamp} / {xtimedelta(parent.segmentlen)}{self.ws}{speed}배속'

                parent.progrdlg.Update(percent, msg)
                if percent == 0:
                    parent.progrdlg.Center()

            elif parent.task == 'concat2':
                percent = round((getseconds(timestamp)/parent.totalduration) * 100)
                if percent < 0:
                    return

                if percent > 100:
                    percent = 100

                msg = f'[{parent.cutmode}] {self.segment_short} 외 {len(parent.segments) - 1}\n{percent}%{self.ws}' \
                      f'{timestamp} / {xtimedelta(parent.totalduration * 1000)}{self.ws}{speed}배속'
                parent.progrdlg.Update(percent, msg)
                if percent == 0:
                    parent.progrdlg.Center()

            else:
                percent = round((getseconds(timestamp)/getseconds(parent.duration)) * 100)
                if percent < 0:
                    return

                if percent > 100:
                    percent = 100

                file = self.file[:FILENAME_LIMIT] + (('…' + os.path.splitext(self.file)[1]) if len(os.path.split(self.file)[1]) > FILENAME_LIMIT else '')
                msg = f'{file}\n' \
                      f'{self.lufs}{self.volume}{self.audio_bitrate}{self.pic}{self.audio}{self.encoding}{self.rotate}{self.orientation}{self.ratio}\n' \
                      f'{percent}%{self.ws}{timestamp} / {parent.duration}{self.ws}{speed}배속'

                parent.progrdlg.Update(percent, msg)
                if percent == 0:
                    parent.progrdlg.Center()

        if parent.task == 'lufs':
            if 'I:' in s:
                lufs = float(s.replace("b'", '').replace('I:', '').replace('LUFS', '')\
                    .replace("\\r\\n'", '').strip())

                if parent.lufs0 == -1:
                    parent.lufs0 = lufs
                else:
                    parent.lufs = lufs

                self.abort = True
                wx.PostEvent(parent, ResultEvent(f'finished-{parent.task}'))

        elif parent.task == 'measurevolume':
            if 'mean_volume:' in s or 'max_volume:' in s:
                s = s.replace("b'", '').replace("\\r\\n'", '').strip()
                if 'mean_volume:' in s:
                    mean_volume = re.search(r'mean_volume:\s*(.+?)\s*dB', s).group(1)
                    parent.volumedetect.append(f'평균 볼륨: {mean_volume} dB')

                if 'max_volume:' in s:
                    max_volume = re.search(r'max_volume:\s*(.+?)\s*dB', s).group(1)
                    parent.volumedetect.append(f'최고 볼륨: {max_volume} dB')
                    self.abort = True
                    wx.PostEvent(parent, ResultEvent(f'finished-{parent.task}'))

        else:
            if 'muxing overhead:' in s:
                self.abort = True
                wx.PostEvent(parent, ResultEvent(f'finished-{parent.task}'))

    def checkprogress2(self):
        parent = self.parent
        if parent.progrdlg.WasCancelled():
            self.abort = True
            wx.PostEvent(parent, ResultEvent(f'cancelled-{parent.task}'))
            self.raise_exception()
            return

        s = str(parent.proc.stdout.readline())
        # print(s)
        if s == "b''":
            percent = 100
            msg = f'{self.infile_short}\n{percent}%'

            parent.progrdlg.Update(percent, msg)
            if percent >= 100:
                self.abort = True
                wx.PostEvent(parent, ResultEvent(f'finished-{parent.task}'))

    def checkprogress3(self):
        parent = self.parent
        if parent.progrdlg.WasCancelled():
            self.abort = True
            wx.PostEvent(parent, ResultEvent(f'cancelled-{parent.task}'))
            self.raise_exception()
            return

        if parent.proc.stdout.readline():
            s = str(parent.proc.stdout.readline())
        else:
            self.abort = True
            wx.PostEvent(parent, ResultEvent(f'finished-{parent.task}'))
            return

        if 'Duration:' in s:
            self.abort = True
            parent.duration = s.split(',')[0].split(': ')[1]
            wx.PostEvent(parent, ResultEvent(f'finished-{parent.task}'))


class Help(wx.Dialog):
    def __init__(self, parent, obj_alias):
        wx.Dialog.__init__(self, parent, -1, '도움말')
        self.parent = parent
        html = wx.html.HtmlWindow(self, -1, size=(440, -1))
        subject = ''
        description = ''

        if obj_alias in ['bitmap', 'pn', 'pn_2']:
            if obj_alias in ['bitmap', 'pn']:
                subject = '왼쪽 창'
                description = '<p>- 입력 파일(작업 대상)이 재생(Play)되는 창입니다.'
            else:
                subject = '오른쪽 창'
                description = '<p>- 출력 파일(작업 결과)이 재생(Play)되는 창입니다.'

            description += '<p>- 마우스 왼쪽 클릭 => 재생(Play)/일시정지(Pause) 토글'
            description += '<p>- 마우스 오른쪽 클릭 => 팝업 메뉴 '

        elif obj_alias in ['slider', 'slider_2']:
            subject = '장면 탐색 / 재생 위치 표시'
            description = """<p>- <strong>동영상 장면 탐색</strong>
<br><br>슬라이더를 움직이면 동영상 재생 위치가 옮겨집니다.
<p>- <strong>동영상 재생 위치 표시</strong>
<br><br>동영상이 재생 위치에 따라 슬라이더 핸들의 위치도 업데이트됩니다."""

        elif obj_alias == 'slider_volume':
            subject = '볼륨'
            description = """<p>- 시스템(스피커)의 현재 볼륨을 기준으로 0~100% 범위 안에서 볼륨을 조절합니다.
<p>- 좌&middot;우 양쪽 창에 공통으로 적용됩니다."""

        elif obj_alias == 'btnOpenAsSource':
            subject = '왼쪽 창에서 열기'
            description = '<p>- 오른쪽 창(출력 파일)의 파일을 왼쪽 창(입력 파일)에서 엽니다.'

        elif obj_alias == 'btnOpenDir':
            subject = '저장폴더 열기'
            description = f'<p>- 저장폴더({parent.savedir})에서 출력 파일(작업 결과)을 엽니다.'

        elif obj_alias == 'btnDefaultApp':
            subject = '기본앱으로 재생'
            description = '<p>- 출력 파일을 기본앱으로 재생합니다.'

        elif obj_alias == 'btnSplitList':
            subject = '분할 목록'
            description = """<p>- 분할 작업으로 생성된 출력 파일들의 목록을 보여줍니다.
<p>- 목록에서 선택된 파일은 오른쪽 창에서 재생됩니다."""

        elif obj_alias == 'btnCutoffList':
            subject = '추출 목록'
            description = """<p>- 추출 작업 목록을 보여줍니다.
<p>- 해당 작업의 파일은 왼쪽 창에서 구간 시작점에서 자동으로 재생되며, 구간 표시(빨간 색 게이지 바)도 자동으로 업데이트됩니다."""

        elif obj_alias in ['btnPrevFile', 'btnNextFile']:
            subject = '이전 파일 / 다음 파일'
            description = """<p>- <strong>이전 파일</strong>
<br><br>현재 열려 있는 파일 바로 전에 열렸던 파일을 불러옵니다.
<p>- <strong>다음 파일</strong>
<br><br>현재 열려 있는 파일 바로 다음에 열렸던 파일을 불러옵니다."""

        elif obj_alias in ['btnGotoBegin', 'btnGotoEnd', 'btnGotoBegin2', 'btnPrev10',
                           'btnNext10', 'btnPrev1', 'btnNext1', 'btnPrevFrame', 'btnNextFrame',
                           'btnZero', 'btnZeroClone', 'btnStop', 'btnPlaySection', 'btnPrevKey',
                           'btnNextKey', 'btnNearFrame']:
            subject = '동영상 재생 / 위치 이동'
            description = """<table>
                <tr><td>◁K</td><td>이전 키프레임으로 이동</td></tr>
                <tr><td>K▷</td><td>다음 키프레임으로 이동</td></tr>
                <tr><td></td></tr>
                <tr><td>◁F</td><td>이전 프레임으로 이동</td></tr>
                <tr><td>⤝F⤞</td><td>가장 가까운 프레임 찾기</td></tr>
                <tr><td>F▷</td><td>다음 프레임으로 이동</td></tr>
                <tr><td></td></tr>
                <tr><td>◁1s</td><td>1초 후진</td></tr>
                <tr><td>1s▷</td><td>1초 전진</td></tr>
                <tr><td></td></tr>
                <tr><td>◁10s</td><td>10초 후진</td></tr>
                <tr><td>10s▷</td><td>10초 전진</td></tr>
                <tr><td></td></tr>
                <tr><td width="100">【←</td><td>구간 시작점으로 이동</td></tr>
                <tr><td>&nbsp;&nbsp;→】</td><td>구간 끝점으로 이동</td></tr>
                <tr><td>&nbsp;&nbsp;|←</td><td>파일 맨 앞으로 이동</td></tr>
                <tr><td></td></tr>
                <tr><td>&nbsp;&nbsp;❚❚</td><td>일시정지(Pause)</td></tr>
                <tr><td>&nbsp;&nbsp;▶</td><td>재생(Play)</td></tr>
                <tr><td>&nbsp;&nbsp;■</td><td>동영상 닫기</td></tr>
                <tr><td>【▶】</td><td>구간 시작점부터 끝점까지 재생 후 정지</td></tr>
                </table>"""

        elif obj_alias in ['btnPrevSegment', 'btnGotoBegin2_2', 'btnZero_2', 'btnPlayEOF', 'btnNextSegment']:
            subject = '동영상 재생 / 파일 이동'
            description = f"""<table><tr><td width="50">❰❰</td><td>이전 동영상으로(분할 결과 중에서)</td></tr>
<tr><td>|▶</td><td>처음부터 재생</td></tr>
<tr><td>❚❚</td><td>일시정지(Pause)</td></tr>
<tr><td>▶</td><td>재생(Play)</td></tr>
<tr><td>▶|</td><td>마지막 {parent.preview_duration}초 재생</td></tr>
<tr><td>❱❱</td><td>다음 동영상으로(분할 결과 중에서)</td></tr></table>"""

        elif obj_alias in ['btnSetBegin', 'btnSetEnd', 'btnGotoBegin', 'btnGotoEnd']:
            subject = '구간 설정'
            description = """<h4>1. 시작점 표시</h4>
<p>- 동영상의 현재 재생 위치에 구간 '<strong>시작</strong>'점을 표시합니다.
<p>- '<strong>직접 스트림 복사</strong>'의 경우 구간 시작점을 <strong>키프레임</strong>에 맞추므로, 
시작점으로 설정하고자 하는 위치에 키프레임이 없으면 그 위치보다 앞에 있는 키프레임이 실제 시작점이 됩니다.
<br><br>'직접 스트림 복사'를 선택했고 동영상의 키프레임 간격이 5초이면, 시작점의 실제 위치는 설정하고자 하는 위치보다 최대 5초까지 앞당겨질 수 있습니다.  
<p>- 만약 시작점으로 설정하고자 하는 위치에 키프레임이 없다면 '<strong>재인코딩</strong>'을 선택하는 것이 좋습니다. 
재인코딩의 경우는 실제 시작점이 설정한 그대로 되기 때문입니다.
<br><br> 
<br>
<h4>2. 끝점 표시</h4>
<p>- 동영상의 현재 재생 위치에 구간 '<strong>끝</strong>'점을 표시합니다.
<p>- 구간 끝점 설정은 '직접 스트림 복사'를 선택한 경우에도 실제 시작점이 <strong>설정한 그대로</strong> 됩니다."""

        elif obj_alias == 'rbCutMode2':
            subject = '인코딩'
            description = """<h4>1. 동영상 생성</h4>
미디어 원본 데이터 → 인코딩 → 먹싱 → 동영상 생성
<br>
<h4>2. 동영상 재생</h4>
동영상 → 디먹싱 → 디코딩 → 재생
<br>
<h4>3. 동영상 변환</h4>
동영상A → 디먹싱 → 디코딩 → (일부 자르거나, 합치거나, 해상도, 비트레이트, 샘플레이트, 길이... 등을 변경하여) 
→ 재인코딩 → 먹싱 → 동영상B 생성
<br>
<h4>4. 용어 설명</h4>
<p>- <strong>인코딩</strong>
<br>멀티미디어의 원본 데이터는 보관, 전송하기에는 용량이 매우 큽니다. 원본 데이터를 특정 헤더와 메타 정보를 추가하고, 
실제 데이터 부분을 압축하여 동영상 파일을 만들게 되는데 이 과정을 인코딩(Encoding) 이라고 합니다.
<br>
<p>- <strong>먹싱</strong>
<br>동영상은 사실 여러 장의 정지 영상과 오디오가 하나의 파일(컨테이너)로 (예: .avi, .mkv, *.mov) 합쳐져 있는 것입니다. 
여러 입력을 하나로 합치는 과정을 먹싱(Muxing) 이라고 합니다.
<br>
<p>- <strong>디먹싱</strong>
<br>먹싱된 동영상을 재생(또는 변환)하기 위해서는 먼저 하나로 합쳐져 있는 정지 영상과 오디오들을 분리해야 하는데 이 과정을 
디먹싱(Demuxing) 이라고 합니다.
<br>
<p>- <strong>디코딩</strong>
<br>디먹싱으로 분리한 후에는 정지 영상과 오디오의 압축을 해제해야 하는데 이 과정을 디코딩(Decoding) 이라고 부릅니다. 
디코딩을 마치면 동영상을 재생(또는 변환)할 수 있게 됩니다."""

        elif obj_alias == 'cbFade':
            subject = '페이드 인/아웃'
            description = """<h4>1. '페이드인', '페이드아웃'의 뜻</h4>
<p>- <strong>페이드인</strong>
<p>어두웠던 화면이 점차 밝아지며 장면이 전환되는 것 
<p>- <strong>페이드아웃</strong>
<p>밝았던 화면이 점차 어두워지며 장면이 전환되는 것
<p>- 시간은 '<strong>설정</strong>' 메뉴에서 조정할 수 있습니다."""

        elif obj_alias in ['cbWaveform', 'btnWaveform']:
            subject = '파형 표시'
            description = """<h4>1. 파형(波形)</h4>
<p>- 출력파일의 오디오 스트림의 파형을 그래프로 표시한 것입니다.
<h4>2. 파형 표시</h4>
<p>- 표시되는 파형의 길이는 '미리보기' 재생시간 설정값과 같습니다.
<p>- '미리보기'에서는 해당 부분(이후/이전)을, '추출'에서는 생성된 파일의 시작과 마지막을 보여줍니다."""

        elif obj_alias == 'btnCutoff':
            subject = '추출'
            description = """<h4>1. 추출 도구</h4>
<p>- FFmpeg의 ffmpeg.exe를 사용합니다. 
<h4>2. 적용</h4>
<p>- <strong>직접 스트림 복사</strong>
<p>ffmpeg.exe -ss 시작시간 -i 입력파일 -to 끝시간 -c copy -copyts -avoid_negative_ts make_zero -map 0 출력파일
<p>시작점을 키프레임에 맞추고, 입력 타임스탬프와 모든 비디오/오디오 트랙 유지함.
<p>- <strong>재인코딩</strong>
<p>ffmpeg.exe -y -ss 시작시간 -i 입력파일 -t 동영상길이 -force_key_frames "'expr:gte(t,n_forced*1)'" -acodec copy 출력파일
<p>키프레임 간격 1초로 함."""

        text = f'<html><body><h3>{subject}</h3>{description}<p style="text-align:right">' \
               f'<wxp module="wx" class="Button"><param name="label" value="닫기">' \
               f'<param name="id" value="ID_OK"></wxp></p></body></html>'
        html.SetPage(text)
        ir = html.GetInternalRepresentation()
        html.SetSize( (ir.GetWidth() + 25, ir.GetHeight() + 0) )
        self.SetClientSize(html.GetSize())
        self.CentreOnParent(wx.BOTH)
        html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.onevtlinkclicked)

    def onevtlinkclicked(self, link):
        url = link.GetLinkInfo().GetHref()
        if url == 'ffplay':
            self.Close()
            self.parent.helpIt2()
            return

        webbrowser.open_new_tab(url)

    def __del__(self):
        pass


class Help2(wx.Dialog):
    def __init__(self, parent, arg):
        title = '도움말' if arg != 9 else f'{TITLE} 정보'
        wx.Dialog.__init__(self, parent, -1, title=title)
        html = wx.html.HtmlWindow(self, -1, size=(440, -1))
        text = ''
        if arg == 1:
            text += """<html><body>
<h3>직접 스트림 복사</h3>
<h4>1. '직접 스트림 복사'의 뜻</h4>
<p>- 일반적인 동영상 변환은 디코딩과 인코딩 과정(→ 재인코딩 Re-encoding)을 거칩니다. <strong>이 과정(디코딩/인코딩)을 생략하고</strong> 
동영상의 일부 구간만을 잘라내거나 컨테이너만을 변경하는 방식을 '직접 스트림 복사' (Direct Stream Copy)라고 합니다.
<br>
<h4>2. '직접 스트림 복사'의 장점</h4>
<p>- <strong>원본의 품질을 그대로 유지할 수 있다</strong>.
<br><br>일반적인 동영상 변환은 <strong>인코딩시 손실 압축</strong>을 하게 되므로 원본보다 품질이 떨어지게 됩니다. 
하지만 '직접 스트림 복사'는 디코딩과 인코딩 과정을 생략하므로 원본의 품질을 그대로 유지합니다.
<p>- <strong>빠르다</strong>.
<br><br>동영상 변환 시간의 <strong>대부분은 디코딩과 인코딩이 차지</strong>합니다. '직접 스트림 복사'는 컨테이너의 해석과 구성, 
저장 장치에 쓰는 시간 정도만을 필요로 하기 때문에 보통의 변환 방식과는 비교할 수 없을 정도로 빠릅니다."""

        elif arg == 2:
            text += """<html><body>
<h3>LUFS</h3>
<h4>1. LUFS의 뜻</h4>
<p>LUFS는 방송 텔레비전 시스템과 기타 동영상 및 음악 스트리밍 서비스에서 오디오 정규화에 사용되는 표준 음량 측정 단위입니다.
<p><strong>인간의 귀가 소리를 인식하는 방식</strong>과 유사한 방식으로 오디오 프로그램 라우드니스를 측정하는 알고리즘이 적용됩니다.
<br><br>
<h4>2. 표준 LUFS를 권장하는 이유</h4>
<p>유튜브의 경우, 업로드된 동영상의 음량이 -14LUFS를 넘을 때에는 정규화를 통해 해당 동영상의 음량을 줄여버립니다. 다음과 같은 목적에서입니다.
<p>- <strong>일관성 유지</strong>: 시청자들이 동일한 채널의 여러 영상을 시청할 때, 소리의 크기가 일정하게 유지되어야 함. LUFS를 기준으로 하면 다양한 영상 간에 일관성 있는 음량을 제공할 수 있음.
<p>- <strong>다이나믹 레인지 조절</strong>: LUFS를 사용하여 노멀라이즈하면 다이나믹 레인지가 줄어들 수 있음. 다이나믹 레인지를 줄이는 것은 음질에 나쁜 영향을 미칠 수 있으므로 적절한 레벨을 유지하는 것이 중요함.
<p>- <strong>시청자 편의성</strong>: 시청자들이 영상을 시청할 때 소리가 너무 크거나 작아서 불편을 느끼지 않도록 하기 위해 LUFS를 기준으로 함.
<br><br>
<h4>3. 스트리밍 서비스별 표준 LUFS</h4>
<p>- 타이달, 아마존 뮤직, 유튜브, 스포티파이: <strong>-14LUFS</strong>
<br>&nbsp;&nbsp;&nbsp;애플뮤직: <strong>-16LUFS</strong>
<p><br><br>LUFS, <cite><a href="https://en.wikipedia.org/wiki/LKFS">https://en.wikipedia.org/wiki/LKFS</a></cite>
<br>LUFS, <cite><a href="https://en.wikipedia.org/wiki/EBU_R_128">https://en.wikipedia.org/wiki/EBU_R_128</a></cite>"""

        elif arg == 9:
            text += f"""<html><body>
<h3>{TITLE}</h3><strong>버전</strong> {VERSION}<br><br>
<p><strong><a href="https://www.ffmpeg.org/">FFmpeg</a></strong> {FFMPEG2}
<p><strong><a href="https://wxpython.org/">wxPython</a></strong> {WXPYTHON}
<p><strong><a href="https://www.python.org/">Python</a></strong> {PYTHON}
<p><strong><a href="https://pyinstaller.org/">PyInstaller</a></strong> {PYINSTALLER}<br><br>
<p>HS Kang
<hr>
<a href="https://ko.wikipedia.org/wiki/FFmpeg">FFmpeg</a>&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://ko.wikipedia.org/wiki/WxPython">wxPython</a>&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://ko.wikipedia.org/wiki/파이썬">Python</a>&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://wikidocs.net/226795">PyInstaller</a>"""

        text += """<p style="text-align:right"><wxp module="wx" class="Button">
    <param name="label" value="닫기">
    <param name="id"    value="ID_OK">
</wxp></p>
</body>
</html>"""

        html.SetPage(text)
        ir = html.GetInternalRepresentation()
        html.SetSize( (ir.GetWidth() + 25, ir.GetHeight() + 0) )
        self.SetClientSize(html.GetSize())
        self.CentreOnParent(wx.BOTH)
        html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.onevtlinkclicked)

    @staticmethod
    def onevtlinkclicked(link):
        url = link.GetLinkInfo().GetHref()
        os.startfile(url)

    def __del__(self):
        pass
        #frame.SetFocus()



class HelpCutMode(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, -1, '도움말')
        html = wx.html.HtmlWindow(self, -1, size=(440, -1))
        text = """<html><body>
<h3>직접 스트림 복사</h3>
<h4>1. '직접 스트림 복사'의 뜻</h4>
<p>- 일반적인 동영상 변환은 디코딩과 인코딩 과정(→ 재인코딩 Re-encoding)을 거칩니다. <strong>이 과정(디코딩/인코딩)을 생략하고</strong> 
동영상의 일부 구간만을 잘라내거나 컨테이너만을 변경하는 방식을 '직접 스트림 복사' (Direct Stream Copy)라고 합니다.
<br>
<h4>2. '직접 스트림 복사'의 장점</h4>
<p>- <strong>원본의 품질을 그대로 유지할 수 있다</strong>.
<br><br>일반적인 동영상 변환은 <strong>인코딩시 손실 압축</strong>을 하게 되므로 원본보다 품질이 떨어지게 됩니다. 
하지만 '직접 스트림 복사'는 디코딩과 인코딩 과정을 생략하므로 원본의 품질을 그대로 유지합니다.
<p>- <strong>빠르다</strong>.
<br><br>동영상 변환 시간의 <strong>대부분은 디코딩과 인코딩이 차지</strong>합니다. '직접 스트림 복사'는 컨테이너의 해석과 구성, 
저장 장치에 쓰는 시간 정도만을 필요로 하기 때문에 보통의 변환 방식과는 비교할 수 없을 정도로 빠릅니다.
<p style="text-align:right"><wxp module="wx" class="Button">
    <param name="label" value="닫기">
    <param name="id"    value="ID_OK">
</wxp></p>
</body>
</html>"""
        html.SetPage(text)
        ir = html.GetInternalRepresentation()
        html.SetSize( (ir.GetWidth() + 25, ir.GetHeight() + 0) )
        self.SetClientSize(html.GetSize())
        self.CentreOnParent(wx.BOTH)
        html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.onevtlinkclicked)

    @staticmethod
    def onevtlinkclicked(link):
        url = link.GetLinkInfo().GetHref()
        webbrowser.open_new_tab(url)

    def __del__(self):
        pass


class HelpFFplay(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, -1, '도움말')
        html = wx.html.HtmlWindow(self, -1, size=(500, -1))
        text = """<html><body>
<h3>ffplay 조작법</h3>
<table>
<tr><td width="150">q, ESC</td><td>종료(<b>q</b>uit)</td></tr>
<!--<tr><td>f</td><td>전체(<b>f</b>ull) 화면 토글</td></tr>-->
<tr><td>p, SPC</td><td>일시정지(<b>p</b>ause)</td></tr>
<tr><td>m</td><td>음소거(<b>m</b>ute) 토글</td></tr>
<tr><td>9, 0</td><td>볼륨을 줄이고 늘림.</td></tr>
<!--<tr><td>/, *</td><td>볼륨을 줄이고 늘림.</td></tr>-->
<!--<tr><td>a</td><td>오디오(<b>a</b>udio) 채널을 순환함.</td></tr>
<tr><td>v</td><td>동영상(<b>v</b>ideo) 채널을 순환함.</td></tr>
<tr><td>t</td><td>자막(sub<b>t</b>itle) 채널을 순환함.</td></tr>
<tr><td>c</td><td>프로그램을 순환함(<b>c</b>ycle).</td></tr>
<tr><td>w</td><td>비디오 필터를 순환하거나 모드를 표시함(sho<b>w</b>).</td></tr>-->
<tr><td>s</td><td>다음 프레임으로 이동함(<b>s</b>tep).</td></tr>
<tr><td>화살표 left/right</td><td>10s 뒤/앞으로 탐색함.</td></tr>
<tr><td>화살표 down/up</td><td>1분 뒤/앞으로 탐색함.</td></tr>
<tr><td>페이지 down/up</td><td>10분 뒤/앞으로 탐색함.</td></tr>
<tr><td>마우스 right click</td><td>너비의 일부에 해당하는 파일의 백분율을 구함.</td></tr>
<tr><td>마우스 left double-click</td><td>전체 화면 토글</td></tr>
<tr><td></td><td></td></tr>
<tr><td></td><td></td></tr>
<tr><td></td><td></td></tr>
</table>
<p style="text-align:right"><wxp module="wx" class="Button">
    <param name="label" value="닫기">
    <param name="id"    value="ID_OK">
</wxp></p>
</body>
</html>"""
        html.SetPage(text)
        ir = html.GetInternalRepresentation()
        html.SetSize( (ir.GetWidth() + 25, ir.GetHeight() + 0) )
        self.SetClientSize(html.GetSize())
        self.CentreOnParent(wx.BOTH)
        html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.onevtlinkclicked)

    @staticmethod
    def onevtlinkclicked(link):
        url = link.GetLinkInfo().GetHref()
        webbrowser.open_new_tab(url)

    def __del__(self):
        pass


class HelpSetupLufs(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, -1, '도움말')
        html = wx.html.HtmlWindow(self, -1, size=(440, -1))
        text = """<html><body>
<h3>LUFS</h3>
<h4>1. LUFS의 뜻</h4>
<p>- LUFS는 방송 텔레비전 시스템과 기타 동영상 및 음악 스트리밍 서비스에서 오디오 정규화에 사용되는 표준 음량 측정 단위입니다.
<p>- <strong>인간의 귀가 소리를 인식하는 방식</strong>과 유사한 방식으로 오디오 프로그램 라우드니스를 측정하는 알고리즘이 적용됩니다.
<br><br>
<h4>2. LUFS는 왜 중요한가</h4>
<p>- 유튜브의 경우, 업로드된 동영상의 음량이 -14LUFS를 넘을 때에는 정규화를 통해 해당 동영상의 음량을 줄여버립니다. 
1LUFS 초과분에 대해 대략 7.5~11% 정도 음량이 줄어듭니다.
<p>- 그러면 반대로 -14LUFS보다 낮게 업로드하면 스트리밍 시 음량이 커지냐고요? 그렇지는 않습니다. 이 경우에는 업로드된 음량 그대로 
스트리밍됩니다.
<p>- 따라서 <strong>-14LUFS에 맞추어</strong> 업로드하면 스트리밍 시 소리가 크게 들리도록 하는 데 도움이 될 것입니다.  
<br><br>
<h4>3. 스트리밍 서비스별 LUFS 목표 수준</h4>
<p>- 타이달, 아마존 뮤직, 유튜브, 스포티파이: <strong>-14LUFS</strong>
<br>&nbsp;&nbsp;&nbsp;애플뮤직: <strong>-16LUFS</strong>
<p><br><br>LUFS, <cite><a href="https://en.wikipedia.org/wiki/LKFS">https://en.wikipedia.org/wiki/LKFS</a></cite>
<br>LUFS, <cite><a href="https://en.wikipedia.org/wiki/EBU_R_128">https://en.wikipedia.org/wiki/EBU_R_128</a></cite>
<p style="text-align:right"><wxp module="wx" class="Button">
    <param name="label" value="닫기">
    <param name="id"    value="ID_OK">
</wxp></p>
</body>
</html>"""
        html.SetPage(text)
        ir = html.GetInternalRepresentation()
        html.SetSize( (ir.GetWidth() + 25, ir.GetHeight()) )
        self.SetClientSize(html.GetSize())
        self.CentreOnParent(wx.BOTH)
        html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.onevtlinkclicked)

    @staticmethod
    def onevtlinkclicked(link):
        url = link.GetLinkInfo().GetHref()
        webbrowser.open_new_tab(url)

    def __del__(self):
        pass


class HelpKLosslesscut(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, -1, 'K-Losslesscut 정보')
        html = wx.html.HtmlWindow(self, -1, size=(440, -1))
        text = f"""<html><body>
<h3>{TITLE}</h3><strong>버전</strong> {VERSION}<br><br>
<p><strong><a href="https://www.ffmpeg.org/">FFmpeg</a></strong> {FFMPEG2}
<p><strong><a href="https://wxpython.org/">wxPython</a></strong> {WXPYTHON}
<p><strong><a href="https://www.python.org/">Python</a></strong> {PYTHON}
<p><strong><a href="https://pyinstaller.org/">PyInstaller</a></strong> {PYINSTALLER}<br><br>
<p>HS Kang
<hr>
<a href="https://ko.wikipedia.org/wiki/FFmpeg">FFmpeg</a>&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://ko.wikipedia.org/wiki/WxPython">wxPython</a>&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://ko.wikipedia.org/wiki/Python">Python</a>&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://en.wikipedia.org/wiki/Pyinstaller">PyInstaller</a>
<p style="text-align:right"><wxp module="wx" class="Button">
    <param name="label" value="닫기">
    <param name="id"    value="ID_OK">
</wxp></p>
</body>
</html>"""
        html.SetPage(text)
        ir = html.GetInternalRepresentation()
        html.SetSize( (ir.GetWidth() + 25, ir.GetHeight() + 0) )
        self.SetClientSize(html.GetSize())
        self.CentreOnParent(wx.BOTH)
        html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.onevtlinkclicked)

    @staticmethod
    def onevtlinkclicked(link):
        url = link.GetLinkInfo().GetHref()
        webbrowser.open_new_tab(url)

    def __del__(self):
        pass


def get_streams(file):
    cmd = f'{FFPROBE} -show_streams -print_format json'.split() + [file]
    output = run(cmd, capture_output=True, text=True, creationflags=0x08000000)
    parsed = json.loads(output.stdout)
    if 'streams' in parsed:
        return parsed['streams']
    else:
        return None

def getmediaduration(path):
    streams = get_streams(path)
    if not streams:
        return None

    duration = None
    video_stream = [stream for stream in streams if stream["codec_type"] == "video"]
    if video_stream:
        if 'duration' in video_stream[0]:
            duration = video_stream[0]['duration']
        else:
            if 'tags' in video_stream[0] and 'DURATION' in video_stream[0]['tags']:
                duration = video_stream[0]['tags']['DURATION']
    else:
        audio_stream = [stream for stream in streams if stream["codec_type"] == "audio"]
        if audio_stream:
            if 'duration' in audio_stream[0]:
                duration = audio_stream[0]['duration']
            else:
                if 'tags' in audio_stream[0] and 'DURATION' in audio_stream[0]['tags']:
                    duration = audio_stream[0]['tags']['DURATION']

    if duration:
        if ':' in duration:
            return round(getseconds(duration), 2)
        else:
            return round(float(duration), 2)
    else:
        return None

def savemediainfo(parent):
    config_ = parent.config
    config_['resolution'] = parent.rd.cbResolution.GetValue()
    config_['timescale'] = parent.rd.cbTimescale.GetValue()
    config_['pixelformat'] = parent.rd.cbPixelformat.GetValue()
    config_['videocodec'] = parent.rd.cbVideocodec.GetValue()
    config_['samplerate'] = parent.rd.cbSamplerate.GetValue()
    config_['channels'] = parent.rd.cbChannels.GetValue()
    config_['audiocodec'] = parent.rd.cbAudiocodec.GetValue()
    with open('config.pickle', 'wb') as f:
        pickle.dump(config_, f)

def getmediainfo(path):
    streams = get_streams(path)
    if not streams:
        return None

    video_stream = [stream for stream in streams if stream["codec_type"] == "video"]
    audio_stream = [stream for stream in streams if stream["codec_type"] == "audio"]
    resolution = f'{video_stream[0]["width"]}x{video_stream[0]["height"]}' if video_stream else ''
    timescale = f'{video_stream[0]["time_base"][2:]}' if video_stream else ''
    pixelformat = f'{video_stream[0]["pix_fmt"]}' if video_stream else ''
    videocodec = f'{video_stream[0]["codec_name"].replace("h264", "H.264/AVC").replace("h265", "H.265/HEVC").replace("vp9", "VP9")}' \
        if video_stream else ''
    samplerate = f'{audio_stream[0]["sample_rate"]}' if audio_stream else ''
    channels = f'{audio_stream[0]["channels"]}' if audio_stream else ''
    audio_codec = f'{audio_stream[0]["codec_name"]}' if audio_stream else ''
    audio_bitrate = int(audio_stream[0]["bit_rate"]) if audio_stream and 'bit_rate' in audio_stream[0] else 0
    video_duration = video_stream[0]["duration"] if video_stream and 'duration' in video_stream[0] else ''
    audio_duration = audio_stream[0]["duration"] if audio_stream and 'duration' in audio_stream[0] else ''

    return [resolution, timescale, pixelformat, videocodec, samplerate, channels, audio_codec, audio_bitrate, video_duration, audio_duration]


class ReencodeDialog(wx.Dialog):
    def __init__(self, parent):
        title = '인코딩' if parent.task == 'concat' else '인코딩'
        wx.Dialog.__init__(self, parent, title = title, size=(300, 435))
        self.parent = parent

        btnrefer = wx.Button(self, -1, '다른 파일 참조...')
        btnrecent = wx.Button(self, -1, '최근 인코딩 적용')

        stresolution = wx.StaticText(self, -1, "    해상도(높이):")
        width, height = parent.player.video_get_size()
        ratio = width / height
        resolutions = [4320, 2160, 1440, 1080, 720, 480, 360, 240, 144]
        resolutions_ = []
        for x in resolutions:
            if x > height:
                continue

            if round(x * ratio) % 2 == 0:
                resolutions_.append(f'{round(x * ratio)}x{x}')
            else:
                if round(x * ratio) > x * ratio:
                    resolutions_.append(f'{round(x * ratio) - 1}x{x}')
                else:
                    resolutions_.append(f'{round(x * ratio) + 1}x{x}')

        self.cbResolution = wx.ComboBox(self, -1, size=(90, -1), choices=resolutions_)

        sttimescale = wx.StaticText(self, -1, "     타임 베이스: 1/ ")
        timescales = ['90000', '30000']
        self.cbTimescale = wx.ComboBox(self, -1, size=(63, -1), choices=timescales)

        stpixelformat = wx.StaticText(self, -1, "        픽셀 형식:")
        pixelformats = ['yuv420p']
        self.cbPixelformat = wx.ComboBox(self, -1, size=(75, -1), choices=pixelformats)

        stvideocodec = wx.StaticText(self, -1, "               코덱:")
        videocodecs = ['H.264/AVC', 'H.265/HEVC']
        self.cbVideocodec = wx.ComboBox(self, -1, size=(97, -1), choices=videocodecs)

        stsamplerate = wx.StaticText(self, -1, "샘플 레이트(Hz):")
        samplerates = ['8000', '11025', '16000', '22050', '32000', '37800', '44056', '44100', '47250', '48000',
                       '50000', '50400', '64000', '88200', '96000', '176400', '192000', '352800', '282400',
                       '5644800', '11289600', '22579200']
        self.cbSamplerate = wx.ComboBox(self, -1, size=(85, -1), choices=samplerates)

        stchannels = wx.StaticText(self, -1, "        채널(개수):")
        channels = ['1', '2']
        self.cbChannels = wx.ComboBox(self, -1, size=(35, -1), choices=channels)

        staudiocodec = wx.StaticText(self, -1, "                코덱:")
        audiocodecs = ['libopus', 'libvorbis', 'libfdk_aac', 'libmp3lame', 'eac3/ac3', 'aac', 'libtwolame', 'mp2']
        self.cbAudiocodec = wx.ComboBox(self, -1, size=(93, -1), choices=audiocodecs)

        info = []
        if self.parent.infile:
            info = getmediainfo(self.parent.infile)

        if info:
            objs = [x for x in self.Children if "wx._core.ComboBox" in f'{x}']
            for i in range(7):
                info_ = f'{info[i]}'
                obj = objs[i]
                items = obj.GetItems()
                if info_ not in items:
                    # 목록에 없는 비디오코덱은 무시
                    if i != 3:
                        items.append(info_)
                        obj.SetItems(items)

                if info_ in items:
                    obj.Select(items.index(info_))

        btnok = wx.Button(self, wx.ID_OK, '실행')
        btncancel = wx.Button(self, wx.ID_CANCEL, '취소')

        if info:
            if not info[0]:
                self.cbResolution.Disable()
                self.cbTimescale.Disable()
                self.cbPixelformat.Disable()
                self.cbVideocodec.Disable()

            elif not info[4]:
                self.cbSamplerate.Disable()
                self.cbChannels.Disable()
                self.cbAudiocodec.Disable()

        inner = wx.BoxSizer(wx.HORIZONTAL)
        inner.Add(stresolution, 0, wx.LEFT | wx.TOP, 10)
        inner.Add(self.cbResolution, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)

        inner2 = wx.BoxSizer(wx.HORIZONTAL)
        inner2.Add(sttimescale, 0, wx.LEFT | wx.TOP, 8)
        inner2.Add(self.cbTimescale, 1, wx.TOP | wx.BOTTOM, 5)

        inner3 = wx.BoxSizer(wx.HORIZONTAL)
        inner3.Add(stpixelformat, 0, wx.LEFT | wx.TOP, 10)
        inner3.Add(self.cbPixelformat, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)

        inner4 = wx.BoxSizer(wx.HORIZONTAL)
        inner4.Add(stvideocodec, 0, wx.LEFT | wx.TOP, 10)
        inner4.Add(self.cbVideocodec, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)

        inner5 = wx.BoxSizer(wx.HORIZONTAL)
        inner5.Add(stsamplerate, 0, wx.LEFT | wx.TOP, 10)
        inner5.Add(self.cbSamplerate, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)

        inner6 = wx.BoxSizer(wx.HORIZONTAL)
        inner6.Add(stchannels, 0, wx.LEFT | wx.TOP, 10)
        inner6.Add(self.cbChannels, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)

        inner7 = wx.BoxSizer(wx.HORIZONTAL)
        inner7.Add(staudiocodec, 0, wx.LEFT | wx.TOP, 10)
        inner7.Add(self.cbAudiocodec, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)

        inner8 = wx.BoxSizer(wx.HORIZONTAL)
        inner8.Add((27, -1))
        inner8.Add(btnrefer, 0, wx.TOP, 10)
        inner8.Add((10, -1))
        inner8.Add(btnrecent, 0, wx.BOTTOM | wx.TOP, 10)

        box = wx.StaticBox(self, -1, '비디오')
        bsizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        bsizer.Add(inner, 0, wx.LEFT | wx.RIGHT, 15)
        bsizer.Add(inner2, 0, wx.LEFT | wx.RIGHT, 15)
        bsizer.Add(inner3, 0, wx.LEFT | wx.RIGHT, 15)
        bsizer.Add(inner4, 0, wx.LEFT | wx.RIGHT, 15)

        box2 = wx.StaticBox(self, -1, '오디오')
        bsizer2 = wx.StaticBoxSizer(box2, wx.VERTICAL)
        bsizer2.Add(inner5, 0, wx.LEFT | wx.RIGHT, 15)
        bsizer2.Add(inner6, 0, wx.LEFT | wx.RIGHT, 15)
        bsizer2.Add(inner7, 0, wx.LEFT | wx.RIGHT, 15)

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btnok)
        btnsizer.AddButton(btncancel)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner8, 0, wx.TOP, 0)
        sizer.Add(bsizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 0)
        sizer.Add(bsizer2, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)

        self.SetSizer(sizer)
        self.Center()
        self.CenterOnScreen()
        btnok.SetFocus()

        btnrecent.Bind(wx.EVT_BUTTON, self.onrecent)
        btnrefer.Bind(wx.EVT_BUTTON, self.onrefer)
        self.Bind(wx.EVT_CLOSE, self.onwindowclose)

    def onrefer(self, evt):
        wildcard = f'비디오/오디오 파일 (*.mp3;*.m4a;*.mov;*.mp4;*.mkv;*.webm;*.avi;*.wmv;*.3gp;*.3g2)|' \
                   f'*.mp3;*.m4a;*.mov;*.mp4;*.mkv;*.webm;*.avi;*.wmv;*.3gp;*.3g2|모든 파일 (*.*)|*.*'
        filedialog = wx.FileDialog(self, '속성을 참조할 파일을 선택하세요.', wildcard=wildcard, style=wx.FD_MULTIPLE)
        if filedialog.ShowModal() != wx.ID_OK:
            return
        path = filedialog.GetPaths()[0]
        filedialog.Destroy()

        info = getmediainfo(path)
        objs = [x for x in self.Children if "ComboBox" in f'{x}']
        for i in range(7):
            if info:
                # resolution
                if not info[0]:
                    if i < 4:
                        continue

                # samplerate
                if not info[4]:
                    if i >= 4:
                        continue

            info_ = info[i]
            obj = objs[i]
            items = obj.GetItems()
            if info_ not in items:
                items.append(info_)
                obj.SetItems(items)

            obj.Select(items.index(info_))

    def onrecent(self, evt):
        config_ = self.parent.config
        resolution = config_['resolution']
        timescale = config_['timescale']
        pixelformat = config_['pixelformat']
        videocodec = config_['videocodec']
        samplerate = config_['samplerate']
        channels = config_['channels']
        audiocodec = config_['audiocodec']
        info = [resolution, timescale, pixelformat, videocodec, samplerate,
                channels, audiocodec]
        objs = [x for x in self.Children if "wx._core.ComboBox" in f'{x}']
        for i in range(7):
            if info[i]:
                info_ = f'{info[i]}'
                obj = objs[i]
                items = obj.GetItems()
                if info_ not in items:
                    items.append(info_)
                    obj.SetItems(items)

                obj.Select(items.index(info_))

    def onwindowclose(self, evt):
        self.Destroy()


class TargetChoice(wx.Dialog):
    def __init__(self, parent):
        title = parent.task_label[parent.task]
        wx.Dialog.__init__(self, parent, title=title, size=(210, 160))
        self.parent = parent

        self.target = ''
        self.auto = False
        stmessage = wx.StaticText(self, -1, '원하는 작업 대상을 선택하세요.')
        self.rbLeft = wx.RadioButton(self, -1, label='왼쪽', size=(60, -1), style = wx.RB_GROUP)
        self.rbLeft.SetToolTip('왼쪽 파일 선택')
        self.rbRight = wx.RadioButton(self, -1, label='오른쪽', size=(60, -1))
        self.rbRight.SetToolTip('오른쪽 파일 선택')

        self.btnok = wx.Button(self, wx.ID_OK, '확인')
        btncancel = wx.Button(self, wx.ID_CANCEL, '취소')
        self.btnok.SetFocus()
        if parent.player.get_state() not in [0, 5] and \
                parent.player_2.get_state() not in [0, 5]:
            stmessage.SetLabel('작업 대상을 선택하세요.')
            self.rbRight.SetValue(True)
            self.target = 'right'

        elif parent.player.get_state() not in [0, 5]:
            self.target = 'left'
            stmessage.SetLabel('작업 대상 : 왼쪽 파일')
            self.rbRight.Disable()

        elif parent.player_2.get_state() not in [0, 5]:
            self.rbRight.SetValue(True)
            self.target = 'right'
            stmessage.SetLabel('작업 대상 : 오른쪽 파일')
            self.rbLeft.Disable()

        inner = wx.BoxSizer(wx.HORIZONTAL)
        inner.Add(stmessage, 0, wx.LEFT, 20)

        inner2 = wx.BoxSizer(wx.HORIZONTAL)
        inner2.Add(self.rbLeft, 0, wx.LEFT, 30)
        inner2.Add(self.rbRight, 0, wx.LEFT, 10)

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(self.btnok)
        btnsizer.AddButton(btncancel)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner, 0, wx.TOP| wx.BOTTOM, 10)
        sizer.Add(inner2, 0, wx.BOTTOM, 10)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10)

        self.SetSizer(sizer)
        self.Center()

        self.Bind(wx.EVT_RADIOBUTTON, self.onradiogroup)
        btncancel.Bind(wx.EVT_BUTTON, self.oncancel)
        self.Bind(wx.EVT_CLOSE, self.onwindowclose)

    def onradiogroup(self, evt):
        target = evt.GetEventObject().GetLabel()
        self.target = 'left' if target == '왼쪽' else 'right'
        self.btnok.SetFocus()

    def oncancel(self, evt):
        self.Close()

    def onwindowclose(self, evt):
        self.target = ''
        self.Destroy()


class MyRearrangeDialog(wx.RearrangeDialog):
    def __init__(self, parent):
        message = "☞ Up / Down 버튼을 사용하여 파일 순서를 조정하세요.\n" \
                  "☞ 체크 표시(✔)를 해제하면 작업 대상에서 제외됩니다."
        self.title = title = "하나로 잇기"
        order = []
        items = []
        wx.RearrangeDialog.__init__(self, parent, message, title, order, items)

        self.parent = parent
        self.btnok = None
        for child in self.Children:
            if child.GetLabel() == 'OK':
                self.btnok = child
                self.btnok.SetLabel('하나로 잇기')

            if child.GetLabel() == 'Cancel':
                child.SetLabel('취소')

        self.segment_mediainfo = []
        self.segment_mediainfo2 = []
        self.items = items
        self.checked_items = []
        self.need_reencode2 = False
        panel = wx.Panel(self)
        self.lc = self.GetList()
        self.lc.SetMinSize((800, 100))

        self.tc = wx.TextCtrl(panel, wx.ID_ANY, f"{len(items)}", size=(40, -1), style=wx.TE_READONLY)
        self.btnAdd = wx.Button(panel, -1, '목록에 추가')
        self.btnRemove = wx.Button(panel, -1, '목록에서 빼기')
        self.btnRemove.Disable()
        st4 = wx.StaticText(panel, -1, "☞ 파일 속성이 불일치하는 경우에는 인코딩이 필요합니다.")
        st4.SetForegroundColour((255,0,0))
        self.btnExamine = wx.Button(panel, -1, '파일 속성 비교')
        self.btnEncode = wx.Button(panel, -1, '인코딩')
        self.btnMediainfo = wx.Button(panel, -1, '미디어 정보')
        self.btnMediainfo.Disable()

        self.st14 = wx.StaticText( panel, -1, "인코딩 기준파일:" )
        self.cb = wx.ComboBox(panel, -1, "", choices=[],
                         style=wx.CB_DROPDOWN | wx.CB_READONLY
                         #| wx.TE_PROCESS_ENTER
                         #| wx.CB_SORT
                         )
        self.cb.SetMinSize((775, -1))

        inner = wx.BoxSizer(wx.HORIZONTAL)
        inner.Add(wx.StaticText(panel, wx.ID_ANY, "선택 파일 수: "), 0, wx.TOP, 8)
        inner.Add(self.tc, 0, wx.TOP, 5)
        inner.Add((10, -1))
        inner.Add(self.btnAdd, 0, wx.TOP, 5)
        inner.Add((10, -1))
        inner.Add(self.btnRemove, 0, wx.TOP, 5)
        inner.Add((10, -1))
        inner.Add(self.btnExamine, 0, wx.TOP, 5)
        inner.Add((10, -1))
        inner.Add(self.btnMediainfo, 0, wx.TOP, 5)

        inner2_0 = wx.BoxSizer(wx.HORIZONTAL)
        inner2_0.Add(st4, 0, wx.BOTTOM, 5)
        inner2_1 = wx.BoxSizer(wx.HORIZONTAL)
        inner2_1.Add(self.st14, 0, wx.RIGHT | wx.TOP, 5)
        inner2_1.Add(self.cb, 1, wx.EXPAND | wx.TOP, 2)

        inner2_2 = wx.BoxSizer(wx.HORIZONTAL)
        inner2_2.Add((1, -1), 1)
        inner2_2.Add(self.btnEncode, 0, wx.TOP, 5)

        self.inner2 = inner2 = wx.BoxSizer(wx.VERTICAL)
        inner2.Add(inner2_0, 0, wx.LEFT, 5)
        inner2.Add(inner2_1, 0, wx.LEFT, 5)
        inner2.Add(inner2_2, 1, wx.EXPAND|wx.LEFT, 5)

        self.sizer = sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner, 0, wx.TOP, 0)
        sizer.Add(inner2, 0, wx.TOP, 10)

        panel.SetSizer(sizer)
        self.AddExtraControls(panel)
        self.Center()

        self.lc.Bind(wx.EVT_CHECKLISTBOX, self.oncheck)
        self.lc.Bind(wx.EVT_LISTBOX, self.onlistbox)
        self.lc.Bind(wx.EVT_CONTEXT_MENU, self.oncontextmenu)
        self.btnAdd.Bind(wx.EVT_BUTTON, self.onadd)
        self.btnRemove.Bind(wx.EVT_BUTTON, self.onremove)
        self.btnExamine.Bind(wx.EVT_BUTTON, self.onexamine)
        self.btnEncode.Bind(wx.EVT_BUTTON, self.onencode)
        self.btnMediainfo.Bind(wx.EVT_BUTTON, self.onmediainfo)
        self.cb.Bind(wx.EVT_COMBOBOX, self.oncombobox)
        self.btnok.Bind(wx.EVT_BUTTON, self.onok)
        self.Bind(wx.EVT_SIZE, self.onsize)
        wx.CallAfter(self.oncheck)

    def onsize(self, event=None):
        pass

    def oncombobox(self, evt):
        #if self.iscompositeconfigurations():
        #    return

        ref_path = self.cb.GetValue()
        idx = self.segment_mediainfo2.index(ref_path)
        ref_mediainfo = self.segment_mediainfo[idx]
        reencode2_paths = [x[0] for x in self.checked_items if x[0] != ref_path]
        for i in range(len(self.segment_mediainfo)):
            if self.segment_mediainfo[i] == ref_mediainfo:
                path = self.segment_mediainfo2[i]
                if path in reencode2_paths:
                    reencode2_paths.remove(path)

        target = '\n▶ '.join(reencode2_paths)
        mediainfo = ''.join(list(ref_mediainfo))
        msg = f'인코딩 대상:\n▶ {target}\n \n기준파일:\n▶ {ref_path}\n\n일치시키는 속성과 값:\n{mediainfo}'
        wx.MessageBox(msg, f'{self.title} - 인코딩')

    def iscompositeconfigurations(self):
        ret = False
        streams = set()
        va = ""
        v = ""
        a = ""
        checkeditems = self.lc.GetCheckedItems()
        for i in checkeditems:
            path = self.lc.GetString(i)
            info = getmediainfo(path)

            has_video = (info[0] != '')
            has_audio = (info[4] != '')
            streams.add((has_video, has_audio))
            if has_video and has_audio:
                va += f'파일 #{i+1}: {path}\n\n'
            elif has_video:
                v += f'파일 #{i+1}: {path}\n\n'
            elif has_audio:
                a += f'파일 #{i+1}: {path}\n\n'

        if len(streams) > 1:
            msg = '비디오/오디오 스트림 구성이 다른 파일들이 섞여 있습니다.\n\n'
            if va:
                msg += f'[비디오/오디오 스트림 모두 있는 파일]\n{va}'

            if v:
                msg += f'[비디오 스트림만 있는 파일]\n{v}'

            if a:
                msg += f'[오디오 스트림만 있는 파일]\n{a}'

            wx.MessageBox(msg, self.title, wx.ICON_EXCLAMATION)
            ret = True

        return ret

    def onok(self, event=None):
        #if self.iscompositeconfigurations():
        #    return

        if self.need_reencode2:
            msg = '인코딩 필요!\n\n파일 속성이 불일치합니다.'
            wx.MessageBox(msg, self.title, wx.ICON_EXCLAMATION)
            return
        else:
            with wx.MessageDialog(self, '\'하나로 잇기\'를 실행할까요?\n\n ', self.title,
                                  style=wx.YES_NO | wx.ICON_QUESTION) as messageDialog:
                if messageDialog.ShowModal() == wx.ID_YES:
                    event.Skip()

    def oncheck(self, evt=None):
        num_checked = len(self.lc.GetCheckedItems())
        self.tc.SetValue(f"{num_checked}")
        self.btnExamine.Enable(num_checked > 1)
        self.btnok.Enable(num_checked > 1)
        self.cb.Clear()
        for i in range(0, len(self.items)):
            if self.lc.IsChecked(i):
                if self.lc.GetString(i) not in self.cb.GetItems():
                    self.cb.Append(self.lc.GetString(i))

        wx.CallAfter(self.onexamine)

    def onexamine(self, event=None):
        msg = ''
        if len(self.lc.GetCheckedItems()) < 2:
            self.need_reencode2 = False
        else:
            self.segment_mediainfo = []
            self.segment_mediainfo2 = []
            self.checked_items = [(self.lc.GetString(x), x) for x in range(len(self.lc.GetItems()))
                             if self.lc.IsChecked(x)]
            num_checked = len(self.checked_items)
            for item in self.checked_items:
                file, idx = item
                streams = get_streams(file)
                if not streams:
                    msg = f'{OPEN_ERROR}\n\n{file}'
                    wx.MessageBox(msg, '미디어 정보', wx.ICON_EXCLAMATION)
                    return

                video_stream = [stream for stream in streams if stream["codec_type"] == "video"]
                audio_stream = [stream for stream in streams if stream["codec_type"] == "audio"]
                tab = ' ' * 4
                if video_stream:
                    mediainfo = (f'{tab}[비디오]\n{tab}{tab}해상도:       '
                                 f'{video_stream[0]["width"]}x{video_stream[0]["height"]}',
                                 f'\n{tab}{tab}타임베이스: {video_stream[0]["time_base"][2:]}',
                                 f'\n{tab}{tab}픽셀 형식:   {video_stream[0]["pix_fmt"]}',
                                 f'\n{tab}{tab}코덱:          '
                                 f'{video_stream[0]["codec_name"].replace("h264", "H.264/AVC").replace("h265", "H.265/HEVC").replace("vp9", "VP9")}')
                else:
                    mediainfo = (f'{tab}[비디오] 없음',)

                if audio_stream:
                    if "channel_layout" in audio_stream[0]:
                        mediainfo += (f'\n{tab}[오디오]\n{tab}{tab}샘플레이트: {audio_stream[0]["sample_rate"]}',
                                     f'\n{tab}{tab}채널:          {audio_stream[0]["channels"]}',
                                     f'\n{tab}{tab}레이아웃:    {audio_stream[0]["channel_layout"]}',
                                     f'\n{tab}{tab}코덱:          {audio_stream[0]["codec_name"]}')
                    else:
                        mediainfo += (f'\n{tab}[오디오]\n{tab}{tab}샘플레이트: {audio_stream[0]["sample_rate"]}',
                                     f'\n{tab}{tab}채널:          {audio_stream[0]["channels"]}',
                                     f'\n{tab}{tab}코덱:          {audio_stream[0]["codec_name"]}')

                else:
                    mediainfo += (f'\n{tab}[오디오] 없음',)

                self.segment_mediainfo.append(mediainfo)
                self.segment_mediainfo2.append(file)

            if len(set(self.segment_mediainfo)) > 1:
                self.need_reencode2 = True
                msg += '인코딩 필요!\n\n파일 속성이 일치하지 않습니다.\n\n'
            else:
                self.need_reencode2 = False
                msg += '파일 속성이 일치합니다.\n \n'

            if event:
                for i in range(num_checked):
                    msg += f'파일 #{i+1}▶ {self.checked_items[i][0]}\n{"".join(self.segment_mediainfo[i])}'
                    msg += '\n\n' if i < num_checked - 1 else ''
                if self.need_reencode2:
                    wx.MessageBox(msg, self.title, wx.ICON_EXCLAMATION)
                else:
                    wx.MessageBox(msg, self.title)

        if self.need_reencode2:
            self.sizer.Show(self.inner2)
            self.sizer.Layout()
            if len(self.cb.GetItems()) > 1:
                self.st14.Enable()
                self.cb.Enable()
        else:
            self.sizer.Hide(self.inner2)
            self.sizer.Layout()

    def onencode(self, evt):
        #if self.iscompositeconfigurations():
        #    return

        self.encodeit()

    def gettargetreencode(self):
        ref_path = self.cb.GetValue()
        idx = self.segment_mediainfo2.index(ref_path)
        ref_mediainfo = self.segment_mediainfo[idx]
        for i in range(len(self.segment_mediainfo)):
            if self.segment_mediainfo[i] == ref_mediainfo:
                path = self.segment_mediainfo2[i]
                if path in self.parent.reencode2_paths:
                    self.parent.reencode2_paths.remove(path)

    def checkstreams(self):
        parent = self.parent
        paths_to_remove = []
        for x in parent.reencode2_paths:
            info = getmediainfo(x)
            # has_video = info[0] != ''
            # has_audio = info[4] != ''
            if parent.basic_streams[0] != (info[0] != '') or parent.basic_streams[1] != (info[4] != ''):
                paths_to_remove.append(x)

        """
        if paths_to_remove:
            msg = '다음 파일은 기준 파일과 스트림 구조가 달라 인코딩 대상에서 제외합니다.\n\n'
            msg += ',\n\n'.join([f'파일 #{x+1}: {paths_to_remove[x]}' for x in range(len(paths_to_remove))])
            wx.MessageBox(msg, '하나로 잇기 - 인코딩', wx.ICON_EXCLAMATION)

            for x in paths_to_remove:
                parent.reencode2_paths.remove(x)
        """
    def encodeit(self):
        parent = self.parent
        path = self.cb.GetValue()
        if not path:
            msg = '기준파일을 지정해주세요.\n\n '
            wx.MessageBox(msg, self.title, style=wx.ICON_EXCLAMATION)
            return

        info = getmediainfo(path)
        # has_video = info[0] != ''
        # has_audio = info[4] != ''
        parent.basic_streams = [info[0] != '', info[4] != '']
        resolution = info[0]
        timescale = info[1]
        pixelformat = info[2]
        videocodec = info[3]
        samplerate = info[4]
        channels = info[5]
        audiocodec = info[6]

        tab = ' ' * 4
        mediainfo = f'{tab}[비디오]\n{tab}{tab}해상도:       {resolution}' \
                    f'\n{tab}{tab}타임베이스: {timescale}' \
                    f'\n{tab}{tab}픽셀 형식:   {pixelformat}' \
                    f'\n{tab}{tab}코덱:          {videocodec}' \
                    f'\n{tab}[오디오]\n{tab}{tab}샘플레이트: {samplerate}' \
                    f'\n{tab}{tab}채널:          {channels}' \
                    f'\n{tab}{tab}코덱:          {audiocodec}'

        #checked_items = [(self.lc.GetString(x), x) for x in range(len(self.lc.GetItems()))
        #                 if self.lc.IsChecked(x)]
        parent.reencode2_paths = [x[0] for x in self.checked_items if x[0] != path]
        self.gettargetreencode()
        target = '\n▶ '.join(parent.reencode2_paths)
        msg = f'인코딩을 실행하겠습니까?\n\n' \
              f'※ 기준파일과 불일치하는 파일들을 기준파일의 속성과 일치시킵니다.\n\n' \
              f'인코딩 대상:\n▶ {target}\n \n기준파일:\n▶ {path}\n\n일치시키는 속성과 값:\n{mediainfo}'

        with wx.MessageDialog(self, msg, '인코딩', style=wx.YES_NO | wx.ICON_QUESTION) as messageDialog:
            if messageDialog.ShowModal() == wx.ID_YES:
                self.checkstreams()

                if not parent.reencode2_paths:
                    msg = '인코딩할 파일이 하나도 없습니다.\n\n '
                    wx.MessageBox(msg, '하나로 잇기 - 인코딩', wx.ICON_EXCLAMATION)
                    return

                config_ = parent.config
                config_['resolution'] = f'{resolution}'
                config_['timescale'] = f'{timescale}'
                config_['pixelformat'] = f'{pixelformat}'
                config_['videocodec'] = f'{videocodec}'
                config_['samplerate'] = f'{samplerate}'
                config_['channels'] = f'{channels}'
                config_['audiocodec'] = f'{audiocodec}'

                parent.reencode2_paths.append((parent.reencode2_paths[:], path, []))
                parent.infile = parent.reencode2_paths.pop(0)
                parent.task = 'reencode2'
                doit(parent)

    def onlistbox(self, evt):
        self.btnRemove.Enable()
        self.btnMediainfo.Enable()

    def onuncheckorcheckall(self, event):
        dowhat = str(event.GetId()).endswith('1')
        for i in range(0, len(self.items)):
            if dowhat:
                self.lc.Check(i, True)
            else:
                self.lc.Check(i, False)

        wx.CallAfter(self.oncheck)

    def onmediainfo(self, evt):
        sel = self.lc.GetSelection()
        self.parent.infile = self.lc.GetString(sel)
        self.parent.task = 'mediainfo'
        doit(self.parent)

    def oncontextmenu(self, evt):
        if len(self.lc.GetItems()) == 0:
            return

        menu = wx.Menu()
        id_uncheckall = 1000
        id_checkall = 1001
        mi1 = wx.MenuItem(menu, id_uncheckall, '전부 해제')
        mi2 = wx.MenuItem(menu, id_checkall, '전부 선택')
        menu.Append(mi1)
        menu.Append(mi2)
        menu.Bind(wx.EVT_MENU, self.onuncheckorcheckall, id=id_uncheckall)
        menu.Bind(wx.EVT_MENU, self.onuncheckorcheckall, id=id_checkall)
        self.PopupMenu(menu)
        menu.Destroy()

    def onadd(self, evt):
        wildcard = f'비디오/오디오 파일 (*.mp3;*.m4a;*.mov;*.mp4;*.mkv;*.webm;*.avi;*.wmv;*.3gp;*.3g2)|' \
                   f'*.mp3;*.m4a;*.m4a;*.mov;*.mp4;*.mkv;*.webm;*.avi;*.wmv;*.3gp;*.3g2|' \
                   f'모든 파일 (*.*)|*.*'
        filedialog = wx.FileDialog(self, '[하나로 잇기] 파일을 선택하세요(복수 선택).', wildcard=wildcard,
                                   style=wx.FD_MULTIPLE)
        if filedialog.ShowModal() != wx.ID_OK:
            return

        paths = filedialog.GetPaths()
        filedialog.Destroy()

        files_added = []
        for path in paths:
            if "'" in path:
                msg = f'파일명에 작은따옴표(\')가 있으면 안됩니다. 파일명을 고친 후에 추가해주세요.\n\n{path}'
                wx.MessageBox(msg, '하나로 잇기 - 인코딩', wx.ICON_EXCLAMATION)
                return

            self.items.append(path)
            self.lc.Append(path)
            self.lc.Check(len(self.items) - 1)
            files_added.append(path)

        if files_added:
            self.oncheck()

    def onremove(self, evt):
        sel = self.lc.GetSelection()
        if sel == -1:
            wx.MessageBox('파일을 선택하세요.\n\n ', self.title, wx.ICON_EXCLAMATION)
            return

        file = self.lc.GetString(sel)
        self.items.remove(file)
        self.lc.Delete(sel)
        cb_items = self.cb.GetItems()
        for i in range(len(cb_items)):
            file_ = cb_items[i]
            if file_ not in self.items:
                if file_ == file:
                    self.cb.Delete(i)

        self.btnRemove.Disable()
        self.btnMediainfo.Disable()
        num_checked = len(self.lc.GetCheckedItems())
        self.btnExamine.Enable(num_checked > 1)
        self.btnok.Enable(num_checked > 1)
        if num_checked < 2:
            self.sizer.Hide(self.inner2)
            self.sizer.Layout()


def isvalid(self, path):
    caption = self.caption if self.caption else self.task_label[self.task]
    info = getmediainfo(path)
    basename = os.path.basename(path)
    if self.task in ['lufs', 'volume', 'measurevolume', 'extractaudio', 'removeaudio',
                     'waveform', 'waveform2', 'reencode', 'preview', 'cutoff']:
        if self.task in ['extractaudio', 'removeaudio']:
            if info[0] == '' and info[4] != '':
                wx.MessageBox(f'오디오 스트림만 있는 파일입니다.\n\n{basename}', caption, wx.ICON_EXCLAMATION)
                return False

        if info[4] == '':
            if info[3] in ['png', 'mjpeg']:
                wx.MessageBox(f'이미지 파일입니다.\n\n{basename}', caption, wx.ICON_EXCLAMATION)
            else:
                wx.MessageBox(f'오디오 스트림이 없는 파일입니다.\n\n{basename}', caption, wx.ICON_EXCLAMATION)

            return False

    return True

def concat_(self):
    self.segments = []
    paths = [self.rd2.lc.GetString(x) for x in range(len(self.rd2.items)) if self.rd2.lc.IsChecked(x)]
    self.rd2.Destroy()
    with open('concat_list.txt', 'w+', encoding='utf8') as f:
        for path in paths:
            self.segments.append(path)
            f.write(f"file '{path}'\n")

        self.segmentcount = 1
        self.totalduration = 0

def doit(self, caption=None, event=None):
    if threading.active_count() > 2:
        wx.CallLater(100, doit, caption, event)
        return

    #############
    # infile 처리
    #############

    if self.player.get_state() == vlc.State.Playing:
        self.pause()

    if self.player_2.get_state() == vlc.State.Playing:
        self.pause_2()

    if caption is None:
        caption = self.task_label[self.task]
        self.caption = ''
    else:
        self.caption = caption

    self.leftright = ''
    if event:
        if self.task in ['saveas', 'lufs', 'volume', 'measurevolume', 'extractaudio', 'removeaudio',
                         'addaudio', 'ncut', 'tcut', 'reencode', 'mediainfo', 'rotate']:
            self.lufs0 = -1
            self.lufs = -1
            self.file0 = ''
            val = 0
            if self.popupmenu != '':
                target = self.popupmenu
            else:
                dlg = TargetChoice(self)
                val = dlg.ShowModal()
                target = dlg.target
                dlg.Destroy()

            if val == wx.ID_OK or target:
                if target == 'right':
                    if not isvalid(self, self.path_2):
                        return

                    self.infile = self.path if self.task == 'volume' else self.path_2

                elif target == 'left':
                    if not isvalid(self, self.path):
                        return

                    self.infile = self.path

                self.leftright = target

            else:
                return

            if self.task in ['addaudio', 'rotate']:
                if self.task == 'addaudio':
                    self.onaddaudio2()

                elif self.task == 'rotate':
                    self.onrotate()

                return

        elif self.task == 'concat':
            self.rd2 = MyRearrangeDialog(self)
            if self.rd2.ShowModal() != wx.ID_OK:
                return

            # MyRearrangeDialog에서 '미디어 정보'를 실행했으면 self.task가 'meadiainfo'로 바뀜.
            # => self.task를 'concat'로 되돌려 놓아야 함.
            self.task = 'concat'
            concat_(self)

    else:
        if self.task in ['orientation', 'ratio']:
            if self.player.get_state() != vlc.State.NothingSpecial:
                if not isvalid(self, self.path):
                    return

                self.infile = self.path

        elif self.task in ['music', 'music2']:
            msg = ''
            wildcard = ''
            if self.task == 'music':
                msg = '[음악 동영상 만들기 #1] 오디오 파일을 선택하세요.'
                wildcard = f'오디오 파일 (*.mp3;*.aac;*.opus;*.vorbis;*.eac3;*.ac3;*.m4a;*.webm;*.flac)|' \
                           f'*.mp3;*.aac;*.opus;*.vorbis;*.eac3;*.ac3;*.m4a;*.webm;*.flac|' \
                           f'모든 파일 (*.*)|*.*'

            elif self.task == 'music2':
                msg = '[음악 동영상 만들기 #2] 이미지 파일을 선택하세요.'
                wildcard = f'그래픽 파일 (*.jpg;*.jpeg;*.png)|*.jpg;*.jpeg;*.png|모든 파일 (*.*)|*.*'

            with wx.FileDialog(self, msg, wildcard=wildcard) as filedialog:
                if filedialog.ShowModal() != wx.ID_OK:
                    return

                path = filedialog.GetPath()
                info = getmediainfo(path)
                if not info:
                    wx.MessageBox(f'파일을 재생할 수 없습니다.\n\n{path}\n \n{OPEN_ERROR}',
                                  TITLE, wx.ICON_EXCLAMATION)
                    if self.task == 'music':
                        self.onaudiopic()
                    else:
                        self.onaudiopic2()
                    return

                # info: 0=>resolution, 1=>timescale, 2=>pixelformat, 3=>videocodec, 4=>samplerate, 5=>channels, 6=>audio_codec, 7=>audio_bitrate, 8=>video_duration, 9=>audio_duration]
                if self.task == 'music':
                    resolution = info[0]
                    samplerate = info[4]
                    if samplerate == '':
                        wx.MessageBox(f'오디오 스트림이 없는 파일입니다.\n\n{path}', caption, wx.ICON_EXCLAMATION)
                        self.onaudiopic()
                        return

                    elif resolution != '' and samplerate != '':
                        wx.MessageBox(f'동영상 파일입니다.\n\n{path}', caption, wx.ICON_EXCLAMATION)
                        self.onaudiopic()
                        return

                    self.infile = path
                    self.onaudiopic2()
                    return

                elif self.task == 'music2':
                    videocodec = info[3]
                    if videocodec == '' or videocodec not in ['png', 'mjpeg']:
                        wx.MessageBox(f'이미지 파일이 아닙니다.\n\n{path}', caption, wx.ICON_EXCLAMATION)
                        self.onaudiopic2()
                        return

                    self.infile2 = path
                    self.onaudiopic3()
                    return

        elif self.task == 'addaudio2':
            msg = '[오디오 추가] 오디오 파일을 선택하세요.'
            wildcard = f'오디오 파일 (*.mp3;*.m4a;*.webm)|*.mp3;*.m4a;*.webm|모든 파일 (*.*)|*.*'

            with wx.FileDialog(self, msg, wildcard=wildcard) as filedialog:
                if filedialog.ShowModal() != wx.ID_OK:
                    return

                path = filedialog.GetPath()
                info = getmediainfo(path)
                if not info:
                    wx.MessageBox(f'파일을 재생할 수 없습니다.\n\n{path}\n \n파일 형식이 지원되지 않거나, '
                                  f'파일 확장명이 올바르지 않거나, 파일이 손상되었을 수 있습니다.',
                                  TITLE, wx.ICON_EXCLAMATION)
                    self.onaddaudio2()
                    return

                samplerate = info[4]
                if samplerate == '':
                    wx.MessageBox(f'오디오 스트림이 없습니다.\n{path}', caption, wx.ICON_EXCLAMATION)
                    self.onaudiopic2()
                    return

                self.infile2 = path
                self.onaddaudio3()
                return

    #############
    # input prompt
    #############
    message2 = '준비 중...'
    if self.task == 'reencode':
        self.rd = ReencodeDialog(self)
        if self.rd.ShowModal() != wx.ID_OK:
            return

        savemediainfo(self)

    elif self.task == 'ncut':
        if event or self.again:
            self.again = False
            with wx.TextEntryDialog(self, '조각의 개수를 입력하세요.', caption) as textentryDialog:
                if textentryDialog.ShowModal() == wx.ID_OK:
                    segmentnum = textentryDialog.Value.strip()
                    if not segmentnum.isnumeric():
                        wx.MessageBox('개수를 입력해주세요.', caption, wx.ICON_EXCLAMATION)
                        self.again = True
                        self.onncut()
                        return

                    segmentnum = int(segmentnum)
                    if segmentnum < 2:
                        wx.MessageBox('개수는 둘 이상이어야 합니다.', caption, wx.ICON_EXCLAMATION)
                        self.again = True
                        self.onncut()
                        return

                    length = self.player.get_length() if self.leftright == 'left' else self.player_2.get_length()
                    if length == -1:
                        length = getmediaduration(self.infile) * 1000

                    segmentlen = math.ceil(length / segmentnum)
                    if segmentlen < 5000:
                        msg = f'길이가 너무 짧습니다({self.segmentlen / 1000}초).\n' \
                              f'적어도 5초는 되도록 분할 개수를 줄여주세요.'
                        wx.MessageBox(msg, caption, wx.ICON_EXCLAMATION)
                        self.again = True
                        self.onncut()
                        return

                    self.again = False
                    self.segmentnum = segmentnum
                    self.segmentlen = segmentlen
                    self.length2 = length
                    self.begin = 0
                    self.segmentcount = 1
                    self.segments = []
                else:
                    self.again = False
                    return

        message2 = f'#{self.segmentcount}/{self.segmentnum} 시작...'

    elif self.task == 'tcut':
        if event or self.again:
            self.again = False
            with wx.TextEntryDialog(self, '조각의 길이(초 또는 시:분:초)를 입력하세요.', caption) \
                    as textentryDialog:
                if textentryDialog.ShowModal() == wx.ID_OK:
                    seconds = 0
                    txt = textentryDialog.Value.strip()
                    cnt = txt.count(':')
                    if cnt == 0:
                        try:
                            seconds = float(txt)
                        except ValueError:
                            wx.MessageBox('숫자를 입력해주세요.', caption, wx.ICON_EXCLAMATION)
                            self.again = True
                            self.ontcut()
                            return

                    elif cnt == 1:
                        m, s = txt.split(':')
                        try:
                            seconds = 60*int(m) + float(s)
                        except ValueError:
                            wx.MessageBox('숫자를 입력해주세요.', caption, wx.ICON_EXCLAMATION)
                            self.again = True
                            self.ontcut()
                            return

                    elif cnt == 2:
                        h, m, s = txt.split(':')
                        try:
                            seconds = 3600*int(h) + 60*int(m) + float(s)
                        except ValueError:
                            wx.MessageBox('숫자를 입력해주세요.', caption, wx.ICON_EXCLAMATION)
                            self.again = True
                            self.ontcut()
                            return

                    segmentlen = seconds * 1000
                    if segmentlen < 5000:
                        msg = f'길이가 너무 짧습니다({segmentlen / 1000}초).\n' \
                              f'분할 길이는 최소 5초입니다.'
                        wx.MessageBox(msg, caption, wx.ICON_EXCLAMATION)
                        self.again = True
                        self.ontcut()
                        return

                    self.again = False
                    self.segmentlen = segmentlen
                    length = getmediaduration(self.infile) * 1000
                    self.segmentnum = math.ceil(length / self.segmentlen)
                    self.length2 = length
                    self.begin = 0
                    self.segmentcount = 1
                    self.segments = []

                else:
                    self.again = False
                    return

        message2 = f'#{self.segmentcount}/{self.segmentnum} 시작...'

    elif self.task == 'concat':
        path = self.segments[self.segmentcount - 1]
        path_short = os.path.split(path)[1][:FILENAME_LIMIT] + \
                          (('…' + os.path.splitext(path)[1]) if len(
                              os.path.split(path)[1]) > FILENAME_LIMIT else '')

        message2 = f'#{self.segmentcount}/{len(self.segments)} 길이 확인 중...' \
                   f'\n{path_short}'

    elif self.task == 'mediainfo':
        streams = get_streams(self.infile)
        if not streams:
            msg = f'{OPEN_ERROR}\n\n{self.infile}'
            wx.MessageBox(msg, '미디어 정보', wx.ICON_EXCLAMATION)
            return

        video_stream = [stream for stream in streams if stream["codec_type"] == "video"]
        audio_stream = [stream for stream in streams if stream["codec_type"] == "audio"]
        s = '비디오:\n'
        s += f'{pformat(video_stream, indent=4)}' if video_stream else '    스트림 없음.'
        s += '\n\n오디오:\n'
        s += f'{pformat(audio_stream, indent=4)}' if audio_stream else '    스트림 없음.'
        msg = f'{self.infile}\n \n{s}'
        ScrolledMessageDialog(self, msg, caption, size=(500, 600)).ShowModal()
        return

    #############
    # outfile 처리
    #############

    same = '입력파일과 출력파일이 같습니다.'
    basename = os.path.basename(self.infile)
    if self.task == 'saveas':
        name, ext = os.path.splitext(basename)
        ext_ = ext.lower()
        path = self.savedir
        wildcard = f'{ext.upper()} 파일 (*{ext_})|*{ext_}|모든 파일 (*.*)|*.*'
        with wx.FileDialog(self, '다른 이름으로 저장', wildcard=wildcard, defaultDir=path,
                           defaultFile=basename, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as filedialog:
            if filedialog.ShowModal() != wx.ID_OK:
                return

            self.outfile = filedialog.GetPath()

        if self.infile == self.outfile:
            wx.MessageBox(f'파일 이름이 그대로입니다.\n{basename}', caption, wx.ICON_EXCLAMATION)
            self.onsaveas(None)
            return

    elif self.task == 'volume':
        if self.file0:
            self.infile = self.file0
            basename = os.path.basename(self.infile)

        self.outfile = f'{self.savedir}\\[vol]{basename}'

    elif self.task == 'orientation':
        self.outfile = f'{self.savedir}\\[orientation]{basename}'

    elif self.task == 'rotate':
        task = ''
        if self.subtask in [0, 1, 2]:
            task = 'rotate ' + ['-90', '+90', '180'][self.subtask]
        elif self.subtask in [3, 4]:
            task = 'flip-' + ['H', 'V'][self.subtask - 3]
        elif self.subtask in [5, 6]:
            task = 'rotate ' + ['-90', '+90'][self.subtask - 5] + ' flip-V'

        self.outfile = f'{self.savedir}\\[{task}]{basename}'

    elif self.task == 'extractaudio':
        name, ext = os.path.splitext(basename)
        self.outfile = f'{self.savedir}\\[audio]{name}.mp3'
        if self.infile == self.outfile:
            wx.MessageBox(f'{same}\n{self.infile}', caption, wx.ICON_EXCLAMATION)
            self.onextractaudio(event)
            return

    elif self.task == 'removeaudio':
        self.outfile = f'{self.savedir}\\[-audio]{basename}'

        if self.infile == self.outfile:
            wx.MessageBox(f'{same}\n{self.infile}', caption, wx.ICON_EXCLAMATION)
            getattr(self, f'on{self.task}')(event)
            return

    elif self.task == 'concat2':
        basename_ = os.path.basename(self.segments[0])
        name, ext = os.path.splitext(basename_)
        self.outfile = f'{self.savedir}\\[concat]{name} 外 {len(self.segments) - 1}{ext}'

    elif self.task == 'music3':
        self.durationcount = 0
        name, ext = os.path.splitext(basename)
        self.outfile = f'{self.savedir}\\[music]{name}.mp4'

    elif self.task == 'addaudio3':
        self.durationcount = 0
        self.outfile = f'{self.savedir}\\[+audio]{basename}'

    elif self.task in ['reencode', 'reencode2']:
        self.outfile = f'{self.savedir}\\[{self.task}]{basename}'

    elif self.task == 'remux':
        name, ext = os.path.splitext(basename)
        self.outfile = f'{self.savedir}\\[remux]{name}.mp4'

    #############
    # thread
    #############
    if self.task in ['concat', 'saveas']:
        self.progrdlg = wx.GenericProgressDialog(caption, message2,
                                                 maximum=100, parent=self,
                                                 style=0 | wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT)
    else:
        self.progrdlg = wx.GenericProgressDialog(caption, message2,
                             maximum=100, parent=self,
                             style=0 | wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_SMOOTH
                             | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_ESTIMATED_TIME
                             | wx.PD_REMAINING_TIME)

    self.worker = WorkerThread(self)
    self.worker.daemon = True
    self.worker.start()


class SetupDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title = '설정', size=(440, 450))
        self.parent = parent
        self.changed = [False] * 6

        st = wx.StaticText(self, -1, "재생시간(초)")
        self.fs = FloatSpin(self, -1, value=parent.config['preview_duration'], min_val=1, max_val=60, increment=1,
                            digits=0, size=(40, -1))

        st2 = wx.StaticText(self, -1, "지속시간(초)")
        self.fs2 = FloatSpin(self, -1, value=parent.config['fade_duration'], min_val=0.5, max_val=5, increment=0.5,
                             digits=1, size=(45, -1))

        btnhelp = wx.Button(self, -1, '?', size=(22, -1))
        btnhelp.SetBackgroundColour((255, 255, 255))
        st3 = wx.StaticText(self, -1, "      LUFS")
        st3_2 = wx.StaticText(self, -1, "(목표치)")
        self.fs3 = FloatSpin(self, -1, value=parent.config['lufs_target'], min_val=-50, max_val=0, increment=0.1,
                             digits=1, size=(60, -1))

        st4 = wx.StaticText(self, -1, "    오디오 비트레이트")
        self.cbBitrate = wx.ComboBox(self, -1, size=(55, -1), choices=parent.audio_bitrates)
        self.cbBitrate.Select(parent.config['audio_bitrate'])

        st5 = wx.StaticText(self, -1, "키프레임 간격(초)")
        self.fs4 = FloatSpin(self, -1, value=parent.config['keyframe_interval'], min_val=1, max_val=10, increment=1,
                             digits=0, size=(45, -1))

        self.st6 = wx.StaticText(self, -1, parent.config['savedir'], size=(295, -1))
        self.btnSavedir = wx.Button(self, -1, '폴더 변경', size=(-1, 25))

        box = wx.StaticBox(self, -1, '미리보기(시작/마지막)')
        bsizer = wx.StaticBoxSizer(box, wx.HORIZONTAL)
        bsizer.Add((270, -1), 0)
        bsizer.Add(st, 0, wx.TOP, 10)
        bsizer.Add(self.fs, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)
        bsizer.Add((5, -1), 0)

        box2 = wx.StaticBox(self, -1, '페이드')
        bsizer2 = wx.StaticBoxSizer(box2, wx.HORIZONTAL)
        bsizer2.Add((264, -1), 0)
        bsizer2.Add(st2, 0, wx.TOP, 10)
        bsizer2.Add(self.fs2, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)
        bsizer2.Add((5, -1), 0)

        box3 = wx.StaticBox(self, -1, 'LUFS 측정 / 볼륨 조정')
        bsizer3 = wx.StaticBoxSizer(box3, wx.HORIZONTAL)
        bsizer3.Add((200, -1), 0)
        bsizer3.Add(st3, 0, wx.TOP, 10)
        bsizer3.Add(btnhelp, 0, wx.TOP, 5)
        bsizer3.Add(st3_2, 0, wx.TOP, 10)
        bsizer3.Add(self.fs3, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)
        bsizer3.Add((5, -1), 0)

        box4 = wx.StaticBox(self, -1, '오디오 추출')
        bsizer4 = wx.StaticBoxSizer(box4, wx.HORIZONTAL)
        bsizer4.Add((205, -1), 0)
        bsizer4.Add(st4, 0, wx.TOP, 10)
        bsizer4.Add(self.cbBitrate, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)
        bsizer4.Add((5, -1), 0)

        box5 = wx.StaticBox(self, -1, '인코딩')
        bsizer5 = wx.StaticBoxSizer(box5, wx.HORIZONTAL)
        bsizer5.Add((236, -1), 0)
        bsizer5.Add(st5, 0, wx.TOP, 10)
        bsizer5.Add(self.fs4, 1, wx.LEFT | wx.TOP | wx.BOTTOM, 5)
        bsizer5.Add((5, -1), 0)

        box6 = wx.StaticBox(self, -1, '저장 폴더')
        bsizer6 = wx.StaticBoxSizer(box6, wx.HORIZONTAL)
        bsizer6.Add((5, -1), 0)
        bsizer6.Add(self.st6, 1, wx.EXPAND | wx.TOP, 10)
        bsizer6.Add(self.btnSavedir, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 5)
        bsizer6.Add((5, -1), 0)

        btnsizer = wx.StdDialogButtonSizer()
        self.btnok = btnok = wx.Button(self, wx.ID_OK, '적용')
        btnok.Enable(False)
        btnsizer.AddButton(btnok)
        self.btncancel = btncancel = wx.Button(self, wx.ID_CANCEL, '취소')
        btncancel.SetFocus()
        btnsizer.AddButton(btncancel)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        # sizer.Add(inner, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.LEFT | wx.RIGHT, 5)
        sizer.Add(bsizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.LEFT, 5)
        sizer.Add(bsizer2, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.LEFT, 5)
        sizer.Add(bsizer3, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.LEFT, 5)
        sizer.Add(bsizer4, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.LEFT, 5)
        sizer.Add(bsizer5, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.LEFT, 5)
        sizer.Add(bsizer6, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.LEFT, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(sizer)
        self.Center()

        self.fs.Bind(wx.lib.agw.floatspin.EVT_FLOATSPIN, self.onevtfloatspin)
        self.fs2.Bind(wx.lib.agw.floatspin.EVT_FLOATSPIN, self.onevtfloatspin2)
        btnhelp.Bind(wx.EVT_BUTTON, self.helplufs)
        self.fs3.Bind(wx.lib.agw.floatspin.EVT_FLOATSPIN, self.onevtfloatspin3)
        self.cbBitrate.Bind(wx.EVT_COMBOBOX, self.oncombobox)
        self.fs4.Bind(wx.lib.agw.floatspin.EVT_FLOATSPIN, self.onevtfloatspin4)
        self.btnSavedir.Bind(wx.EVT_BUTTON, self.onsavedir)
        self.CenterOnScreen()
        self.Bind(wx.EVT_CLOSE, self.onwindowclose)

    def helplufs(self, evt):
        dlg = Help2(self, 2)
        dlg.ShowModal()
        dlg.Destroy()

    def onevtfloatspin(self, evt):
        self.changed[0] = (self.fs.GetValue() != self.parent.config['preview_duration'])
        self.setcontrols()

    def onevtfloatspin2(self, evt):
        self.changed[1] = (self.fs2.GetValue() != self.parent.config['fade_duration'])
        self.setcontrols()

    def onevtfloatspin3(self, evt):
        self.changed[2] = (self.fs3.GetValue() != self.parent.config['lufs_target'])
        self.setcontrols()

    def oncombobox(self, evt):
        sel = self.cbBitrate.GetSelection()
        self.changed[3] = (sel != self.parent.config['audio_bitrate'])
        bps = ''
        bitrate = self.parent.audio_bitrates[sel]
        if bitrate:
            bps = f'({bitrate})'

        self.parent.menu_audio_extract.SetItemLabel(f'추출{bps}...')
        self.setcontrols()

    def onevtfloatspin4(self, evt):
        self.changed[4] = (self.fs4.GetValue() != self.parent.config['keyframe_interval'])
        self.setcontrols()

    def onsavedir(self, evt=None):
        dlg = wx.DirDialog(self, "작업 결과를 저장할 폴더를 선택하세요.", style=wx.DD_DIR_MUST_EXIST)
        val = dlg.ShowModal()
        path = dlg.GetPath()
        dlg.Destroy()
        if val == wx.ID_OK:
            self.st6.SetLabel(path)
            self.changed[5] = (self.st6.GetLabel() != self.parent.config['savedir'])
            self.setcontrols()

    def setcontrols(self):
        if sum(self.changed) > 0:
            self.btnok.Enable()
            self.btnok.SetFocus()
        else:
            self.btnok.Disable()
            self.btncancel.SetFocus()

    def onwindowclose(self, evt):
        self.Destroy()


class TransformDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title = '가로형/세로형 변환', size=(240, 260))
        self.parent = parent

        parent.subtask = '세로형으로'
        parent.direction = '상·하 여백 넣기'
        self.rbPortraitStyle = wx.RadioButton(self, -1, label='세로형으로', style = wx.RB_GROUP)
        self.rbLandscapeStyle = wx.RadioButton(self, -1, label='가로형으로')

        width, height = parent.player.video_get_size()
        if width > height:
            self.rbLandscapeStyle.Disable()
            self.rbPortraitStyle.SetValue(True)
        elif width < height:
            self.rbPortraitStyle.Disable()
            self.rbLandscapeStyle.SetValue(True)
            parent.subtask = '가로형으로'
        else:
            if parent.orientation['style'] == '가로형으로':
                self.rbLandscapeStyle.SetValue(True)
                parent.subtask = '가로형으로'

        self.rbFitWidth = wx.RadioButton(self, -1, label='상·하 여백 넣기', style = wx.RB_GROUP)
        self.rbFitHeight = wx.RadioButton(self, -1, label='좌·우 잘라 내기')
        parent.direction = '상·하 여백 넣기'
        if parent.orientation['fit'] == '좌·우 잘라 내기':
            self.rbFitHeight.SetValue(True)
            parent.direction = '좌·우 잘라 내기'

        box = wx.StaticBox(self, -1, size=(150, 60))
        bsizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        bsizer.Add(self.rbPortraitStyle, 0,  wx.TOP, 5)
        bsizer.Add(self.rbLandscapeStyle, 0, wx.TOP, 10)

        box2 = wx.StaticBox(self, -1, size=(150, 60))
        bsizer2 = wx.StaticBoxSizer(box2, wx.VERTICAL)
        bsizer2.Add(self.rbFitWidth, 0,  wx.TOP, 5)
        bsizer2.Add(self.rbFitHeight, 0, wx.TOP, 10)

        btnsizer = wx.StdDialogButtonSizer()
        self.btnok = btnok = wx.Button(self, wx.ID_OK, '확인')
        btnsizer.AddButton(btnok)
        self.btncancel = btncancel = wx.Button(self, wx.ID_CANCEL, '취소')
        btnsizer.AddButton(btncancel)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(bsizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 15)
        sizer.Add(bsizer2, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.BOTTOM, 15)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10)

        self.SetSizer(sizer)
        self.Center()
        self.CenterOnScreen()
        self.Bind(wx.EVT_RADIOBUTTON, self.onradiogroup)
        self.Bind(wx.EVT_CLOSE, self.onwindowclose)

    def onradiogroup(self, evt):
        label = evt.GetEventObject().GetLabel()
        parent = self.parent
        if label in ['세로형으로', '가로형으로']:
            parent.subtask = label
            parent.orientation['style'] = label
        elif label in ['상·하 여백 넣기', '좌·우 잘라 내기']:
            parent.direction = label
            parent.orientation['fit'] = label

    def onwindowclose(self, evt):
        self.Destroy()

class HelpMenu(wx.Frame):
    def __init__(self, parent):
        title = "도움말"
        super(HelpMenu, self).__init__(
            parent, -1, title=title, size=wx.Size(800, 500), style=wx.CAPTION |
            wx.CLOSE_BOX | wx.SYSTEM_MENU | wx.RESIZE_BORDER)

        splitter = wx.SplitterWindow(self)
        window1 = NavBar(splitter)
        window2 = HtmlPanel(splitter)
        splitter.SplitVertically(window1, window2)
        splitter.SetSashGravity(0.5)
        splitter.SetMinimumPaneSize(200)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self.Show()

class HtmlPanel(wx.Panel):
    def __init__(self, parent):
        super(HtmlPanel, self).__init__(parent)

        self.browser = wx.html2.WebView.New(self)
        htmlszr = wx.BoxSizer(wx.VERTICAL)
        htmlszr.Add(self.browser, 1, wx.EXPAND)
        with open(r'.\data\help\index.html', encoding='utf8') as f:
            contents = f.read()
            self.browser.SetPage(contents, '')

        self.SetSizer(htmlszr)


class NavTree(wx.TreeCtrl):
    def __init__(self, parent, id, pos, size, style):
        super(NavTree, self).__init__(parent, id, pos, size, style)


class NavBar(wx.Panel):
    def __init__(self, parent):
        super(NavBar, self).__init__(parent)
        # '해상도 변경',
        self.labs = [TITLE,
                     '파일',
                            '파일 열기', '다른 이름으로 저장', '설정', '', '', '', '', '', '',
                     '도구',
                            'LUFS 측정 / 볼륨 조정', '볼륨 측정', '오디오 처리', '분할',
                            '인코딩', '회전 / 뒤집기', '가로형/세로형 변환', '종횡비 변경', '캡처',
                            '키프레임 타임스탬프', '미디어 정보', '하나로 잇기', '음악 동영상 만들기', '리먹싱(=>mp4)']

        self.pages = ['index.html',
                      None,
                            'open.html', 'saveas.html', 'setup.html', None, None, None, None, None, None,
                      None,
                            'lufs.html', 'volume.html', 'audio.html', 'ncut_tcut.html',
                            'reencode.html', 'rotate.html', 'orientation.html', 'ratio.html', 'capture.html',
                            'keyframes.html', 'mediainfo.html', 'concat.html', 'musicvideo.html', 'remux.html']
        self.tree = NavTree(
            self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TR_HAS_BUTTONS)
        self.parent = parent
        self.root = self.tree.AddRoot(self.labs[0])
        self.menu1 = self.tree.AppendItem(self.root, self.labs[1])
        self.tree.AppendItem(self.menu1, self.labs[2])
        self.tree.AppendItem(self.menu1, self.labs[3])
        self.tree.AppendItem(self.menu1, self.labs[4])
        self.menu2 = self.tree.AppendItem(self.root, self.labs[11])
        self.tree.AppendItem(self.menu2, self.labs[12])
        self.tree.AppendItem(self.menu2, self.labs[13])
        self.tree.AppendItem(self.menu2, self.labs[14])
        self.tree.AppendItem(self.menu2, self.labs[15])
        self.tree.AppendItem(self.menu2, self.labs[16])
        self.tree.AppendItem(self.menu2, self.labs[17])
        self.tree.AppendItem(self.menu2, self.labs[18])
        self.tree.AppendItem(self.menu2, self.labs[19])
        self.tree.AppendItem(self.menu2, self.labs[20])
        self.tree.AppendItem(self.menu2, self.labs[21])
        self.tree.AppendItem(self.menu2, self.labs[22])
        self.tree.AppendItem(self.menu2, self.labs[23])
        self.tree.AppendItem(self.menu2, self.labs[24])
        self.tree.AppendItem(self.menu2, self.labs[25])
        self.tree.ExpandAll()
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.onchanged)

        self.treeszr = wx.BoxSizer(wx.VERTICAL)
        self.treeszr.Add(self.tree, 1, wx.EXPAND)
        self.SetSizer(self.treeszr)

    def onchanged(self, event):
        item = event.GetItem()
        label = self.tree.GetItemText(item)
        if label:
            pass
        else:
            return
        index = self.labs.index(label)
        contents = ''
        if self.pages[index]:
            with open(f'.\\data\\help\\{self.pages[index]}', encoding='utf8') as f:
                contents = f.read()

        # self.parent.GetWindow2().html.SetPage(contents)
        self.parent.GetWindow2().browser.SetPage(contents, '')

