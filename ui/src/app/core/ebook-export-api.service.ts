import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { EbookFormats, ExportEbookResult } from './models';

@Injectable({ providedIn: 'root' })
export class EbookExportApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  formats(): Observable<EbookFormats> {
    return this.http.get<EbookFormats>(`${this.baseUrl}/ebooks/formats`);
  }

  // A series identifier produces one ebook per work, not a single file.
  exportEbook(
    identifier: string,
    target: string,
    source: string,
    format: string
  ): Observable<ExportEbookResult> {
    return this.http.post<ExportEbookResult>(`${this.baseUrl}/ebooks/export`, {
      identifier,
      target,
      source,
      format
    });
  }
}
