import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../environments/environment';
import { PronunciationDictSummary, PronunciationEntry } from './models';

@Injectable({ providedIn: 'root' })
export class PronunciationApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  listDictionaries(folder: string): Observable<PronunciationDictSummary[]> {
    const params = new HttpParams().set('folder', folder);
    return this.http
      .get<{ dictionaries: PronunciationDictSummary[] }>(`${this.baseUrl}/pronunciations`, {
        params
      })
      .pipe(map((response) => response.dictionaries));
  }

  getDictionary(path: string): Observable<Record<string, PronunciationEntry>> {
    const params = new HttpParams().set('path', path);
    return this.http
      .get<{ entries: Record<string, PronunciationEntry> }>(
        `${this.baseUrl}/pronunciations/dict`,
        { params }
      )
      .pipe(map((response) => response.entries));
  }

  saveDictionary(
    path: string,
    entries: Record<string, PronunciationEntry>
  ): Observable<Record<string, PronunciationEntry>> {
    return this.http
      .post<{ entries: Record<string, PronunciationEntry> }>(
        `${this.baseUrl}/pronunciations/dict`,
        { path, entries }
      )
      .pipe(map((response) => response.entries));
  }
}
