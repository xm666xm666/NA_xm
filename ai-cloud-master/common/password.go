package common

import (
	"crypto/rand"
	"errors"
	"fmt"
	"math/big"
	"strings"
	"unicode"
	"unicode/utf8"
)

const (
	minimumPasswordLength = 8
	maximumPasswordLength = 20
	// maximumBcryptPasswordBytes prevents bcrypt from rejecting or truncating UTF-8 passwords.
	maximumBcryptPasswordBytes = 72
	passwordUppercase          = "ABCDEFGHJKLMNPQRSTUVWXYZ"
	passwordLowercase          = "abcdefghijkmnopqrstuvwxyz"
	passwordDigits             = "23456789"
	passwordSpecial            = "!@#$%^&*()-_=+"
)

var commonWeakPasswords = map[string]struct{}{
	"000000": {}, "111111": {}, "123456": {}, "12345678": {},
	"123456789": {}, "1234567890": {}, "1q2w3e4r": {}, "1qaz2wsx": {},
	"abc123": {}, "admin": {}, "admin123": {}, "admin1234": {},
	"admin1234!": {}, "admin@123": {}, "letmein": {}, "password": {},
	"password1": {}, "password1!": {}, "password123": {}, "password@123": {},
	"qwerty": {}, "qwerty123": {}, "qwerty123!": {}, "root": {},
	"root123": {}, "test1234": {}, "welcome": {},
}

// ValidatePasswordStrength enforces the password policy before hashing.
func ValidatePasswordStrength(password string) error {
	length := utf8.RuneCountInString(password)
	if length < minimumPasswordLength {
		return errors.New("密码长度至少为8个字符")
	}
	if length > maximumPasswordLength {
		return errors.New("密码长度不能超过20个字符")
	}
	if len(password) > maximumBcryptPasswordBytes {
		return errors.New("密码 UTF-8 编码不能超过72字节")
	}
	if _, weak := commonWeakPasswords[strings.ToLower(strings.TrimSpace(password))]; weak {
		return errors.New("密码过于常见，请更换更强的密码")
	}

	var upper, lower, digit, special bool
	for _, char := range password {
		switch {
		case unicode.IsUpper(char):
			upper = true
		case unicode.IsLower(char):
			lower = true
		case unicode.IsDigit(char):
			digit = true
		case unicode.IsPunct(char) || unicode.IsSymbol(char):
			special = true
		}
	}

	var categories int
	for _, present := range []bool{upper, lower, digit, special} {
		if present {
			categories++
		}
	}
	if categories < 3 {
		return errors.New("密码必须包含大写字母、小写字母、数字、特殊符号中的至少三类")
	}
	return nil
}

// GenerateStrongPassword creates a random password containing all four categories.
func GenerateStrongPassword(length int) (string, error) {
	if length < minimumPasswordLength {
		return "", fmt.Errorf("密码长度不能小于%d个字符", minimumPasswordLength)
	}
	if length > maximumPasswordLength {
		return "", fmt.Errorf("密码长度不能超过%d个字符", maximumPasswordLength)
	}

	sets := []string{passwordUppercase, passwordLowercase, passwordDigits, passwordSpecial}
	password := make([]byte, 0, length)
	for _, set := range sets {
		char, err := randomPasswordCharacter(set)
		if err != nil {
			return "", err
		}
		password = append(password, char)
	}

	allCharacters := strings.Join(sets, "")
	for len(password) < length {
		char, err := randomPasswordCharacter(allCharacters)
		if err != nil {
			return "", err
		}
		password = append(password, char)
	}
	for index := len(password) - 1; index > 0; index-- {
		randomIndex, err := rand.Int(rand.Reader, big.NewInt(int64(index+1)))
		if err != nil {
			return "", fmt.Errorf("打乱随机密码: %w", err)
		}
		other := int(randomIndex.Int64())
		password[index], password[other] = password[other], password[index]
	}

	generated := string(password)
	if err := ValidatePasswordStrength(generated); err != nil {
		return "", fmt.Errorf("校验随机密码: %w", err)
	}
	return generated, nil
}

// randomPasswordCharacter selects one byte from an ASCII character set.
func randomPasswordCharacter(characterSet string) (byte, error) {
	index, err := rand.Int(rand.Reader, big.NewInt(int64(len(characterSet))))
	if err != nil {
		return 0, fmt.Errorf("生成随机密码字符: %w", err)
	}
	return characterSet[index.Int64()], nil
}
