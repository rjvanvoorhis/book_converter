import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  CopyEditResult,
  ExtractedTextSummary,
  ExtractTextResult,
  LoadEbookResult,
  SaveTextReviewResult,
  TextReviewFlag
} from './models';

@Injectable({ providedIn: 'root' })
export class TextExtractionApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  loadEbook(identifier: string, source: string): Observable<LoadEbookResult> {
    const params = new HttpParams().set('identifier', identifier).set('source', source);
    return this.http.get<LoadEbookResult>(`${this.baseUrl}/books`, { params });
  }

  extractText(
    identifier: string,
    target: string,
    source: string
  ): Observable<ExtractTextResult> {
    return this.http.post<ExtractTextResult>(`${this.baseUrl}/extracted-texts`, {
      identifier,
      target,
      source
    });
  }

  // Runs in place over an already-extracted folder (identifier here is the
  // folder path, not the original source) - review the resulting diffs
  // before committing to speech generation.
  copyedit(identifier: string, editor: string): Observable<CopyEditResult> {
    return this.http.post<CopyEditResult>(`${this.baseUrl}/extracted-texts/copyedit`, {
      identifier,
      editor
    });
  }

  listExtractedTexts(folder: string): Observable<ExtractedTextSummary[]> {
    const params = new HttpParams().set('folder', folder);
    return this.http
      .get<{ texts: ExtractedTextSummary[] }>(`${this.baseUrl}/extracted-texts/library`, {
        params
      })
      .pipe(map((response) => response.texts));
  }

  deleteExtractedText(path: string): Observable<void> {
    const params = new HttpParams().set('path', path);
    return this.http.delete<void>(`${this.baseUrl}/extracted-texts`, { params });
  }

  saveTextReview(
    path: string,
    flag: TextReviewFlag | null,
    note: string | null
  ): Observable<SaveTextReviewResult> {
    return this.http.post<SaveTextReviewResult>(`${this.baseUrl}/extracted-texts/review`, {
      path,
      flag,
      note
    });
  }
}
