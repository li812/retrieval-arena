import { Link, useLocation } from 'react-router';

export default function NotFound() {
  const { pathname } = useLocation();
  return (
    <div className="page">
      <section className="panel">
        <div className="empty-state">
          <div className="notfound-code" aria-hidden="true">
            404
          </div>
          <h2 className="empty-title">Page not found</h2>
          <p className="empty-text">
            There is nothing at <code>/app{pathname}</code>. The link may be old, or the page hasn’t
            been built yet.
          </p>
          <Link className="btn btn-primary" to="/">
            Go to Home
          </Link>
        </div>
      </section>
    </div>
  );
}
