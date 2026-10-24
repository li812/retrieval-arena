import { createBrowserRouter, type RouteObject } from 'react-router';

import Bots from '@/routes/Bots';
import Collections from '@/routes/Collections';
import Home from '@/routes/Home';
import Lab from '@/routes/Lab';
import NotFound from '@/routes/NotFound';
import RouteError from '@/routes/RouteError';
import Settings from '@/routes/Settings';

import { AppShell } from './AppShell';
import { RequireAuth } from './RequireAuth';

/** The SPA is served at /app/ (vite `base`, FastAPI mount). */
export const BASENAME = '/app';

export const routes: RouteObject[] = [
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    errorElement: <RouteError />,
    children: [
      { index: true, element: <Home /> },
      { path: 'bots', element: <Bots /> },
      { path: 'collections', element: <Collections /> },
      { path: 'lab', element: <Lab /> },
      { path: 'settings', element: <Settings /> },
      { path: '*', element: <NotFound /> },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes, { basename: BASENAME });
}
