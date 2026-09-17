/**
 * Legacy /login route.
 *
 * Redirects to /sign-in, which is the canonical sign-in page.
 * This file exists to avoid 404s from any old bookmarks or links.
 */
export { default } from "../sign-in/page";
