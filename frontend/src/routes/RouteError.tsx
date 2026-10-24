import { isRouteErrorResponse, useRouteError } from 'react-router';

import { BrandMark } from '@/components/Primitives';

/** Last-resort boundary for render errors inside routes. */
export default function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : 'Unknown error';
  return (
    <div className="content">
      <div className="page">
        <section className="panel">
          <div className="empty-state" role="alert">
            <BrandMark />
            <h2 className="empty-title">Something broke on this page</h2>
            <p className="empty-text">
              <code>{message}</code>
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => window.location.reload()}
            >
              Reload the page
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
