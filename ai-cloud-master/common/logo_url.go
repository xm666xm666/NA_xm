package common

import (
	"errors"
	"net/url"
	"path"
	"strings"
)

var errInvalidLogoURL = errors.New("Logo 图片地址仅允许本站相对路径，例如 /logo.png")

// NormalizeLogoURL restricts logos to normalized root-relative paths on this site.
func NormalizeLogoURL(value string) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return "", nil
	}
	isRootRelative := strings.HasPrefix(value, "/") && !strings.HasPrefix(value, "//")
	if !isRootRelative || strings.Contains(value, `\`) {
		return "", errInvalidLogoURL
	}

	parsed, err := url.Parse(value)
	if err != nil {
		return "", errInvalidLogoURL
	}
	hasInvalidTarget := parsed.IsAbs() || parsed.Host != "" || strings.Contains(parsed.Path, `\`)
	if hasInvalidTarget {
		return "", errInvalidLogoURL
	}
	parsed.Path = path.Clean(parsed.Path)
	parsed.RawPath = ""
	if !strings.HasPrefix(parsed.Path, "/") {
		return "", errInvalidLogoURL
	}
	return parsed.String(), nil
}
