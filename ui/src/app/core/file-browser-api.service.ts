import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { FileBrowserListing } from './models';

@Injectable({ providedIn: 'root' })
export class FileBrowserApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  browse(path?: string): Observable<FileBrowserListing> {
    const params = path ? new HttpParams().set('path', path) : undefined;
    return this.http.get<FileBrowserListing>(`${this.baseUrl}/files/browse`, { params });
  }
}
