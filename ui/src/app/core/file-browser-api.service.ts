import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { FileBrowserListing } from './models';

@Injectable({ providedIn: 'root' })
export class FileBrowserApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  browse(path?: string, extensions?: string[]): Observable<FileBrowserListing> {
    let params = new HttpParams();
    if (path) {
      params = params.set('path', path);
    }
    if (extensions?.length) {
      params = params.set('extensions', extensions.join(','));
    }
    return this.http.get<FileBrowserListing>(`${this.baseUrl}/files/browse`, { params });
  }
}
