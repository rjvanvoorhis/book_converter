import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map, switchMap, takeWhile, timer } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  AudiobookTaskState,
  CreateAudiobookRequest,
  CreateAudiobookResult,
  CreateAudiobookTask,
  CreateSampleRequest,
  VoiceProfile
} from './models';

const POLL_INTERVAL_MS = 1500;

@Injectable({ providedIn: 'root' })
export class AudiobookApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  listVoices(engine: string, ttsProvider: string): Observable<VoiceProfile[]> {
    const params = new HttpParams().set('tts_provider', ttsProvider);
    return this.http
      .get<{ voices: VoiceProfile[] }>(`${this.baseUrl}/engines/${engine}/voices`, {
        params
      })
      .pipe(map((response) => response.voices));
  }

  createAudiobook(request: CreateAudiobookRequest): Observable<CreateAudiobookTask> {
    return this.http.post<CreateAudiobookTask>(`${this.baseUrl}/audiobooks`, request);
  }

  createSample(request: CreateSampleRequest): Observable<CreateAudiobookTask> {
    return this.http.post<CreateAudiobookTask>(`${this.baseUrl}/audiobooks/sample`, request);
  }

  getSampleAudio(taskId: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/audiobooks/sample/${taskId}/audio`, {
      responseType: 'blob'
    });
  }

  cancelTask(taskId: string): Observable<AudiobookTaskState> {
    return this.http.put<AudiobookTaskState>(
      `${this.baseUrl}/audiobooks/tasks/${taskId}/status`,
      { status: 'cancelled' }
    );
  }

  getTaskStatus<TResult = CreateAudiobookResult>(
    taskId: string
  ): Observable<AudiobookTaskState<TResult>> {
    return this.http.get<AudiobookTaskState<TResult>>(
      `${this.baseUrl}/audiobooks/tasks/${taskId}`
    );
  }

  /** Polls a task until it reaches a terminal state, emitting each state along the way. */
  pollTaskUntilDone<TResult = CreateAudiobookResult>(
    taskId: string
  ): Observable<AudiobookTaskState<TResult>> {
    return timer(0, POLL_INTERVAL_MS).pipe(
      switchMap(() => this.getTaskStatus<TResult>(taskId)),
      takeWhile((state) => state.status === 'pending' || state.status === 'running', true)
    );
  }
}
